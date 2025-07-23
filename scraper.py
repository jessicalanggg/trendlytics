import csv
import time
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
import os

def _num(x):
    """Convert string numbers with K/M suffixes to integers"""
    if isinstance(x, str):
        x = x.replace(',', '').strip()  # Remove commas and whitespace
        if 'K' in x:
            return int(float(x.replace('K', '')) * 1_000)
        elif 'M' in x:
            return int(float(x.replace('M', '')) * 1_000_000)
        elif 'B' in x:
            return int(float(x.replace('B', '')) * 1_000_000_000)
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return 0

def setup_driver():
    """Setup Chrome driver with proper options"""
    options = uc.ChromeOptions()
    
    # Essential options for headless operation
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Speed up loading
    options.add_argument("--window-size=1920,1080")
    
    # User agent to avoid detection
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # For production, use headless mode
    if os.getenv('PRODUCTION', False):
        options.add_argument("--headless=new")
    
    try:
        return uc.Chrome(options=options)
    except Exception as e:
        print(f"[SCRAPER] Failed to setup Chrome driver: {e}")
        return None

def scroll_for_videos(driver, target=20, max_scrolls=50):
    """Scroll and collect video links"""
    video_links = set()
    scroll_count = 0
    
    while len(video_links) < target and scroll_count < max_scrolls:
        # Scroll down
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(1.5, 2.5))
        
        # Find video links
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
            for link in links:
                href = link.get_attribute("href")
                if href and "/video/" in href:
                    video_links.add(href)
        except Exception:
            pass
        
        scroll_count += 1
        print(f"[SCRAPER] Found {len(video_links)} videos after {scroll_count} scrolls")
        
        # Break if we haven't found new videos in the last few scrolls
        if scroll_count > 10 and len(video_links) < 5:
            break
    
    return list(video_links)[:target]

def extract_video_data(driver, video_url, retries=3):
    """Extract data from a single video"""
    for attempt in range(retries):
        try:
            driver.get(video_url)
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            
            # Extract likes
            likes = "0"
            like_selectors = [
                "strong[data-e2e='like-count']",
                "[data-e2e='like-count']",
                ".like-count",
                "*[title*='like']"
            ]
            for selector in like_selectors:
                try:
                    likes = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if likes:
                        break
                except:
                    continue
            
            # Extract comments
            comments = "0"
            comment_selectors = [
                "strong[data-e2e='comment-count']",
                "[data-e2e='comment-count']",
                ".comment-count",
                "*[title*='comment']"
            ]
            for selector in comment_selectors:
                try:
                    comments = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if comments:
                        break
                except:
                    continue
            
            # Extract description
            description = ""
            desc_selectors = [
                "[data-e2e='browse-video-desc']",
                "[data-e2e='video-desc']",
                ".video-meta-caption",
                "h1[data-e2e='browse-video-desc']",
                "meta[name='description']"
            ]
            for selector in desc_selectors:
                try:
                    if "meta" in selector:
                        description = driver.find_element(By.CSS_SELECTOR, selector).get_attribute("content")
                    else:
                        description = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if description:
                        break
                except:
                    continue
            
            if not description:
                description = "N/A"
            
            return {
                "url": video_url,
                "likes": likes or "0",
                "comments": comments or "0",
                "description": description[:500]  # Limit description length
            }
            
        except Exception as e:
            print(f"[SCRAPER] Attempt {attempt + 1} failed for {video_url}: {str(e)}")
            time.sleep(2)
    
    # Return default data if all attempts failed
    return {
        "url": video_url,
        "likes": "0",
        "comments": "0", 
        "description": "Failed to extract"
    }

def scrape_profile_stats(driver, username):
    """Scrape basic profile statistics"""
    url = f"https://www.tiktok.com/@{username}"
    
    try:
        driver.get(url)
        
        # Wait for profile to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)
        
        # Extract profile data with multiple selector fallbacks
        name = username
        try:
            name_selectors = [
                "h1[data-e2e='user-title']",
                "h2[data-e2e='user-title']",
                ".share-title",
                "h1"
            ]
            for selector in name_selectors:
                try:
                    name_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    if name_elem.text.strip():
                        name = name_elem.text.strip()
                        break
                except:
                    continue
        except:
            pass
        
        # Extract followers
        followers = "N/A"
        try:
            follower_selectors = [
                "[data-e2e='followers-count']",
                ".number[title*='Follow']",
                "*[title*='Follow']"
            ]
            for selector in follower_selectors:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, selector)
                    followers = elem.text.strip() or elem.get_attribute("title")
                    if followers:
                        break
                except:
                    continue
        except:
            pass
        
        # Extract following
        following = "N/A"
        try:
            following_selectors = [
                "[data-e2e='following-count']",
                ".number[title*='Following']"
            ]
            for selector in following_selectors:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, selector)
                    following = elem.text.strip() or elem.get_attribute("title")
                    if following:
                        break
                except:
                    continue
        except:
            pass
        
        # Extract total likes
        total_likes = "N/A"
        try:
            likes_selectors = [
                "[data-e2e='likes-count']",
                ".number[title*='Like']"
            ]
            for selector in likes_selectors:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, selector)
                    total_likes = elem.text.strip() or elem.get_attribute("title")
                    if total_likes:
                        break
                except:
                    continue
        except:
            pass
        
        return {
            "username": username,
            "name": name,
            "followers": followers,
            "following": following,
            "total_likes": total_likes
        }
        
    except Exception as e:
        print(f"[SCRAPER] Profile extraction failed: {str(e)}")
        return {
            "username": username,
            "name": username,
            "followers": "N/A",
            "following": "N/A", 
            "total_likes": "N/A"
        }

def scrape_tiktok(username):
    """Main scraping function - called by Flask app"""
    print(f"[SCRAPER] Starting scrape for @{username}")
    
    driver = None
    try:
        driver = setup_driver()
        if not driver:
            return {"error": "Failed to setup Chrome driver. Please check Chrome installation."}
        
        # Get profile stats
        profile_stats = scrape_profile_stats(driver, username)
        
        # Get video links
        print("[SCRAPER] Scrolling for video links...")
        video_links = scroll_for_videos(driver, target=15)
        
        if not video_links:
            return {"error": "No videos found. Profile might be private or doesn't exist."}
        
        print(f"[SCRAPER] Found {len(video_links)} videos, extracting data...")
        
        # Extract video data
        video_data = []
        for i, video_url in enumerate(video_links, 1):
            print(f"[SCRAPER] Processing video {i}/{len(video_links)}")
            data = extract_video_data(driver, video_url)
            video_data.append(data)
            
            # Add delay between requests
            time.sleep(random.uniform(1, 2))
        
        # Save to CSV
        csv_filename = f"{username}_tiktok_videos.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as file:
            if video_data:
                writer = csv.DictWriter(file, fieldnames=["url", "likes", "comments", "description"])
                writer.writeheader()
                writer.writerows(video_data)
        
        # Calculate engagement rate
        try:
            total_likes = sum(_num(v["likes"]) for v in video_data)
            total_comments = sum(_num(v["comments"]) for v in video_data)
            estimated_views = total_likes * 12  # Rough estimate
            
            if estimated_views > 0:
                engagement_rate = ((total_likes + total_comments) / estimated_views) * 100
                profile_stats["engagement_rate"] = f"{engagement_rate:.2f}%"
            else:
                profile_stats["engagement_rate"] = "N/A"
        except:
            profile_stats["engagement_rate"] = "N/A"
        
        print(f"[SCRAPER] ✅ Successfully scraped {len(video_data)} videos")
        return profile_stats
        
    except Exception as e:
        print(f"[SCRAPER] ❌ Error: {str(e)}")
        return {"error": f"Scraping failed: {str(e)}"}
        
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    # For testing
    import sys
    if len(sys.argv) > 1:
        username = sys.argv[1]
        result = scrape_tiktok(username)
        print(f"Result: {result}")
    else:
        print("Usage: python scraper.py <username>")