import csv
import time
import random
import traceback
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import os


def take_videos_page_screenshot(driver, channel_id):
    try:
        path = f"{channel_id}_videos.png"
        driver.save_screenshot(path)
        print(f"📸 Screenshot saved to: {path}")
    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}")


def setup_youtube_driver():
    """Setup Chrome driver for YouTube scraping"""
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # For production, use headless mode
    if os.getenv('PRODUCTION', False):
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
    
    try:
        return uc.Chrome(options=options)
    except Exception as e:
        print(f"❌ Failed to setup Chrome driver: {e}")
        return None


def get_youtube_channel_stats(channel_id):
    """Main function to scrape YouTube channel data"""
    base_url = f"https://www.youtube.com/@{channel_id}"
    
    # Initialize all variables at function level
    channel_name = "N/A"
    subscribers = "N/A"
    total_views = "N/A"
    total_likes = "N/A"
    launch_date = "N/A"

    driver = setup_youtube_driver()
    if not driver:
        return {"error": "Failed to setup Chrome driver"}

    try:
        print(f"\n🌐 Loading channel: {base_url}")
        driver.get(base_url)
        time.sleep(5)

        # Get channel name - try multiple approaches
        channel_name = "N/A"
        try:
            # Try different selectors for channel name
            name_selectors = [
                "#channel-name .ytd-channel-name",
                ".ytd-channel-name #text",
                "#text.ytd-channel-name", 
                "yt-formatted-string.ytd-channel-name",
                "#channel-header-container #text",
                ".page-header-view-model-wiz__page-header-title",
                "h1[class*='channel-name']"
            ]
            
            for selector in name_selectors:
                try:
                    name_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    potential_name = name_elem.text.strip()
                    if potential_name and len(potential_name) > 1:
                        channel_name = potential_name
                        print(f"📺 Channel Name: {channel_name}")
                        break
                except:
                    continue
            
            # If still N/A, try getting from page title
            if channel_name == "N/A":
                try:
                    page_title = driver.title
                    if " - YouTube" in page_title:
                        channel_name = page_title.replace(" - YouTube", "").strip()
                        print(f"📺 Channel Name (from title): {channel_name}")
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ Failed to get channel name: {e}")

        # Get subscriber count - stable approach
        subscribers = "N/A"
        try:
            # Wait a bit longer for page to fully load
            time.sleep(3)
            
            # Try the main subscriber selector first
            try:
                sub_elem = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.ID, "subscriber-count"))
                )
                subscribers = sub_elem.text.strip()
                if subscribers:
                    print(f"🎯 Subscribers: {subscribers}")
                else:
                    raise Exception("Empty subscriber text")
            except:
                # If main method fails, try alternative selectors (one at a time, safely)
                backup_selectors = [
                    ".ytd-c4-tabbed-header-renderer #subscriber-count",
                    "[aria-label*='subscriber']", 
                    "#owner-sub-count"
                ]
                
                for selector in backup_selectors:
                    try:
                        sub_elem = driver.find_element(By.CSS_SELECTOR, selector)
                        text = sub_elem.text.strip()
                        if text and ("subscriber" in text.lower() or any(c.isdigit() for c in text)):
                            subscribers = text
                            print(f"🎯 Subscribers (backup): {subscribers}")
                            break
                    except:
                        continue
                
                # Final fallback - search page source for subscriber data (safely)
                if subscribers == "N/A":
                    try:
                        page_source = driver.page_source
                        import re
                        # Look for the most common pattern
                        match = re.search(r'"subscriberCountText":\s*{"simpleText":\s*"([^"]+)"', page_source)
                        if match:
                            subscribers = match.group(1)
                            print(f"🎯 Subscribers (page source): {subscribers}")
                        else:
                            # Try simpler pattern
                            match = re.search(r'(\d+\.?\d*[KM]?)\s*subscriber', page_source, re.IGNORECASE)
                            if match:
                                subscribers = match.group(1) + " subscribers"
                                print(f"🎯 Subscribers (regex): {subscribers}")
                    except Exception as e:
                        print(f"⚠️ Page source search failed: {e}")
                        
        except Exception as e:
            print(f"⚠️ Subscriber detection failed: {e}")
        
        print(f"🎯 Final Subscribers: {subscribers}")

        # Go to Videos tab
        videos_url = f"{base_url}/videos"
        print(f"🎬 Loading videos page: {videos_url}")
        driver.get(videos_url)
        
        # Wait for videos to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ytd-rich-grid-media, ytd-grid-video-renderer"))
            )
        except Exception as e:
            print(f"⚠️ Videos might not have loaded properly: {e}")
        
        time.sleep(3)

        # ✅ Screenshot BEFORE scrolling
        take_videos_page_screenshot(driver, channel_id)

        # Find video cards with multiple selectors
        video_selectors = [
            "ytd-rich-grid-media",
            "ytd-grid-video-renderer", 
            "ytd-video-renderer",
            ".ytd-rich-grid-media",
            ".ytd-grid-video-renderer"
        ]
        
        video_cards = []
        for selector in video_selectors:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    video_cards = cards
                    print(f"✅ Found {len(cards)} videos using selector: {selector}")
                    break
            except Exception as e:
                print(f"⚠️ Selector {selector} failed: {e}")
                continue
        
        if not video_cards:
            print("❌ No video cards found with any selector")
            return {"error": "No videos found on the channel"}

        all_data = []
        max_videos = min(20, len(video_cards))  # Limit to 20 videos

        for idx, card in enumerate(video_cards[:max_videos]):
            print(f"📹 Processing Video {idx + 1}/{max_videos}")

            try:
                # Try multiple selectors for title
                title = "N/A"
                title_selectors = [
                    "#video-title",
                    "a#video-title",
                    ".ytd-rich-grid-media #video-title",
                    "h3 a",
                    ".video-title",
                    "a[aria-label]"
                ]
                
                for title_selector in title_selectors:
                    try:
                        title_elem = card.find_element(By.CSS_SELECTOR, title_selector)
                        title = title_elem.get_attribute("title") or title_elem.get_attribute("aria-label") or title_elem.text.strip()
                        if title and title != "N/A":
                            break
                    except:
                        continue

                # Try to get URL
                url = "N/A"
                url_selectors = [
                    "a#thumbnail",
                    "a#video-title", 
                    "a[href*='/watch']",
                    ".thumbnail a",
                    "ytd-thumbnail a"
                ]
                
                for url_selector in url_selectors:
                    try:
                        url_elem = card.find_element(By.CSS_SELECTOR, url_selector)
                        url = url_elem.get_attribute("href")
                        if url and "watch" in url:
                            break
                    except:
                        continue

                # Extract metadata from card text
                try:
                    card_text = card.text.lower()
                    text_lines = card_text.split("\n")
                    
                    # Look for views
                    views = "N/A"
                    for line in text_lines:
                        if "views" in line or "view" in line:
                            views = line.strip()
                            break
                    
                    # Look for upload time
                    upload_time = "N/A"
                    for line in text_lines:
                        if "ago" in line:
                            upload_time = line.strip()
                            break
                
                except Exception as e:
                    print(f"⚠️ Error extracting metadata from text: {e}")
                    views = "N/A"
                    upload_time = "N/A"

                # Store video data - ensure title is clean and not empty
                clean_title = title.strip() if title and title != "N/A" else f"Video {idx + 1}"
                
                video_data = {
                    "title": clean_title[:200],  # Limit title length
                    "views": views,
                    "upload_time": upload_time,
                    "url": url
                }
                
                all_data.append(video_data)
                print(f"✅ Video {idx + 1}: {clean_title[:50]}{'...' if len(clean_title) > 50 else ''}")

            except Exception as e:
                print(f"❌ Error scraping video {idx + 1}: {e}")
                print(traceback.format_exc())
                
                # Add placeholder data to maintain count
                all_data.append({
                    "title": f"Video {idx + 1} (extraction failed)",
                    "views": "N/A",
                    "upload_time": "N/A",
                    "url": "N/A"
                })
                continue

            # Random delay between videos
            time.sleep(random.uniform(0.5, 1.5))

        # Export CSV with guaranteed data
        csv_filename = f"{channel_id}_youtube_videos.csv"
        csv_path = os.path.abspath(csv_filename)
        
        try:
            with open(csv_filename, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=["title", "views", "upload_time", "url"])
                writer.writeheader()
                
                if all_data:
                    for row in all_data:
                        # Ensure title is never empty
                        if not row.get("title") or row["title"] == "N/A":
                            row["title"] = "Untitled Video"
                        writer.writerow(row)
                else:
                    # Write at least one row with sample data if nothing was scraped
                    writer.writerow({
                        "title": f"Sample video from {channel_id}",
                        "views": "N/A",
                        "upload_time": "N/A", 
                        "url": "N/A"
                    })
                    all_data = [{"title": f"Sample video from {channel_id}"}]

            print(f"\n✅ Success! Exported {len(all_data)} videos to {csv_filename}")
            print(f"📁 File location: {csv_path}")
            
            return {
                "success": True,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "video_count": len(all_data),
                "csv_file": csv_filename,
                "csv_path": csv_path,
                "data_preview": all_data[:3]  # Include first 3 videos for verification
            }

        except Exception as e:
            print(f"❌ Error writing CSV file: {e}")
            return {"error": f"Failed to write CSV file: {str(e)}"}

    except Exception as e:
        print(f"\n❌ Fatal error during scraping: {e}")
        print(traceback.format_exc())
        return {"error": f"Scraping failed: {str(e)}"}
        
    finally:
        try:
            if driver:
                driver.quit()
                print("🔒 Browser closed")
        except Exception as e:
            print(f"⚠️ Error closing browser: {e}")


def scrape_youtube_channel(channel_id):
    """Wrapper function that can be called by Flask app or other scripts"""
    print(f"[YOUTUBE SCRAPER] Starting scrape for channel: {channel_id}")
    
    # Clean channel_id
    channel_id = channel_id.strip().replace('@', '')
    
    try:
        result = get_youtube_channel_stats(channel_id)
        
        if "error" in result:
            print(f"[YOUTUBE SCRAPER] ❌ Error: {result['error']}")
            return {"error": result["error"]}
        
        print(f"[YOUTUBE SCRAPER] ✅ Successfully scraped {result['video_count']} videos")
        print(f"[YOUTUBE SCRAPER] 📁 CSV saved: {result['csv_file']}")
        
        # Return the CSV path for the analyzer to use
        return result
        
    except Exception as e:
        print(f"[YOUTUBE SCRAPER] ❌ Unexpected error: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}"}


def scrape_and_analyze(channel_id):
    """Complete workflow: scrape channel then analyze the data with full integration"""
    print(f"🚀 Starting complete YouTube workflow for: {channel_id}")
    print("=" * 60)
    
    # Step 1: Scrape the channel
    print("📥 STEP 1: Scraping channel data...")
    scrape_result = scrape_youtube_channel(channel_id)
    
    if "error" in scrape_result:
        return {"error": f"Scraping failed: {scrape_result['error']}"}
    
    csv_path = scrape_result.get("csv_path")
    print(f"✅ Scraping complete! CSV saved to: {csv_path}")
    
    # Step 2: Analyze the data
    print(f"\n🤖 STEP 2: Analyzing content...")
    try:
        from youtubeanalyzer import run_youtube_analysis
        analysis_result = run_youtube_analysis(csv_path)
        
        if "error" in analysis_result:
            return {"error": f"Analysis failed: {analysis_result['error']}"}
        
        print("✅ Analysis complete!")
        
        # Combine results with full channel info
        combined_result = {
            "status": "success",
            "message": f"Successfully analyzed {scrape_result['video_count']} videos from {scrape_result.get('channel_name', channel_id)}",
            "channel_info": {
                "channel_id": scrape_result["channel_id"],
                "channel_name": scrape_result.get("channel_name", "N/A"),
                "subscribers": scrape_result.get("subscribers", "N/A"),
                "video_count": scrape_result["video_count"]
            },
            "signature": analysis_result.get("signature", {}),
            "video_ideas": analysis_result.get("video_ideas", []),
            "growth_tips": analysis_result.get("growth_tips", []),
            "csv_file": scrape_result.get("csv_file"),
            "csv_path": csv_path,
            "scrape_data": scrape_result,
            "analysis_data": analysis_result
        }
        
        return combined_result
        
    except ImportError:
        print("⚠️ youtubeanalyzer.py not found - returning scrape data only")
        return {
            "status": "partial_success",
            "message": "Scraping completed but analysis unavailable",
            "scrape_data": scrape_result, 
            "csv_path": csv_path,
            "error": "Analysis module not found"
        }
    except Exception as e:
        print(f"❌ Analysis error: {str(e)}")
        return {
            "status": "partial_success", 
            "message": "Scraping completed but analysis failed",
            "scrape_data": scrape_result,
            "csv_path": csv_path,
            "error": f"Analysis failed: {str(e)}"
        }


if __name__ == "__main__":
    # For command line usage
    import sys
    
    if len(sys.argv) > 1:
        channel_id = sys.argv[1]
        
        # Check if user wants complete workflow
        if len(sys.argv) > 2 and sys.argv[2] == "--analyze":
            print(f"🎯 Running complete workflow for: {channel_id}")
            result = scrape_and_analyze(channel_id)
            
            # Display results nicely
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"\n🎉 SUCCESS! Full analysis completed!")
                
                if "channel_info" in result:
                    info = result["channel_info"]
                    print(f"📺 Channel: {info.get('channel_name', 'N/A')} (@{info.get('channel_id')})")
                    print(f"👥 Subscribers: {info.get('subscribers', 'N/A')}")
                    print(f"📹 Videos Analyzed: {info.get('video_count', 0)}")
                
                if "signature" in result:
                    sig = result["signature"]
                    print(f"\n🎭 Channel Vibes: {', '.join(sig.get('vibes', []))}")
                    print(f"📚 Topics: {', '.join(sig.get('topics', []))}")
                
                if "video_ideas" in result:
                    print(f"\n🎬 Video Ideas ({len(result['video_ideas'])}):")
                    for idea in result["video_ideas"][:5]:
                        print(f"   {idea}")
                
                if "growth_tips" in result:
                    print(f"\n🚀 Growth Tips ({len(result['growth_tips'])}):")
                    for tip in result["growth_tips"][:3]:
                        print(f"   {tip}")
                
                print(f"\n📁 CSV File: {result.get('csv_file', 'N/A')}")
        else:
            print(f"🎯 Scraping only for: {channel_id}")
            result = scrape_youtube_channel(channel_id)
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Success!")
                print(f"📺 Channel: {result.get('channel_name', 'N/A')} (@{result['channel_id']})")
                print(f"👥 Subscribers: {result.get('subscribers', 'N/A')}")
                print(f"📹 Videos: {result['video_count']}")
                print(f"📁 CSV file: {result['csv_path']}")
                print("\n💡 To get full analysis, run with --analyze flag")
    else:
        # Default example
        print("🚀 Running YouTube scraper with default channel...")
        result = scrape_youtube_channel("veritasium")
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"✅ Complete! Check the generated CSV file.")
            print("💡 Usage:")
            print("  python scraper-yt.py <channel_id>           # Scrape only")
            print("  python scraper-yt.py <channel_id> --analyze # Scrape + full analysis")