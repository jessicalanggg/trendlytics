import json
import time
import itertools
import re
import unicodedata
import requests
import os
import math
from collections import Counter, defaultdict
import pandas as pd

# DeepSeek API Integration
from openai import OpenAI

# Initialize DeepSeek client
client = OpenAI(
    api_key="sk-90b8397488ed4726a77af9f4b0da34f4",
    base_url="https://api.deepseek.com"
)

def _num(x):
    """Convert string numbers with K/M suffixes to integers"""
    if isinstance(x, str):
        x = x.replace(',', '').strip()
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

def _safe_parse_json(line: str):
    """Safely parse JSON from a line of text"""
    line = line.strip()
    if not line or line.startswith("```"):
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', line)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None

_GEO_TERMS = set("""
omaha papillion council bluffs nebraska kansas texas california florida illinois
newyork york alberta ontario london sydney melbourne delhi mumbai
""".split())

def _is_geo_kw(phrase: str) -> bool:
    """Check if a phrase contains geographical terms"""
    tokens = re.findall(r"[a-z]+", phrase.lower())
    return any(tok in _GEO_TERMS for tok in tokens)

HASHTAG_RE = re.compile(r"#(\w{2,40})")

def extract_topics_keywords(
    descriptions: list[str],
    max_per_req: int = 6,  # Reduced batch size for better reliability
    sleep_s: float = 1.5,  # Increased delay
    trim_chars: int = 250   # Shorter descriptions to avoid token limits
) -> pd.DataFrame:
    """
    • Calls DeepSeek for topics & keywords.
    • Extracts native hashtags from each description.
    • Cleans geo / long / dup keywords.
    """
    out_rows, to_do = [], descriptions.copy()
    print(f"[TIKTOK ANALYZER] Processing {len(descriptions)} descriptions...")

    sys_msg = (
        "You are a social-media expert. For EACH video description, "
        "analyze and return ONE JSON per line: "
        "{\"topics\":[\"topic1\",\"topic2\"],\"keywords\":[\"keyword1\",\"keyword2\"]} "
        "Keep topics broad (like 'lifestyle', 'comedy', 'education'). "
        "Keep keywords specific and relevant. No locations."
    )

    batch_count = 0
    while to_do:
        batch, to_do = to_do[:max_per_req], to_do[max_per_req:]
        batch_count += 1
        
        # Clean and prepare descriptions
        cleaned_batch = []
        for desc in batch:
            # Remove excessive whitespace and special characters
            cleaned = re.sub(r'\s+', ' ', desc[:trim_chars]).strip()
            cleaned_batch.append(cleaned)
        
        joined = "\n---\n".join(cleaned_batch)
        
        print(f"[TIKTOK ANALYZER] Processing batch {batch_count} ({len(batch)} items)...")

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=1500,  # Limit response length
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": f"Descriptions:\n{joined}"}
                ]
            )
            
            response_content = resp.choices[0].message.content
            print(f"[TIKTOK ANALYZER] DeepSeek response length: {len(response_content)}")
            
            # Parse response line by line
            lines = response_content.replace("```json", "").replace("```", "").splitlines()
            json_lines = [ln for ln in lines if ln.strip() and ("{" in ln or "}" in ln)]
            
            print(f"[TIKTOK ANALYZER] Found {len(json_lines)} potential JSON lines")
            
            parsed_objs = []
            for line in json_lines:
                parsed = _safe_parse_json(line)
                if parsed and "topics" in parsed and "keywords" in parsed:
                    parsed_objs.append(parsed)
            
            print(f"[TIKTOK ANALYZER] Successfully parsed {len(parsed_objs)} objects")

            # Process successful parses
            for i, (desc, parsed) in enumerate(zip(batch, parsed_objs)):
                if i >= len(parsed_objs):  # Safety check
                    parsed = {"topics": ["general"], "keywords": ["content"]}
                
                cleaned_kw = [
                    kw for kw in dict.fromkeys(parsed.get("keywords", []))
                    if not _is_geo_kw(kw) and len(kw.split()) <= 3 and len(kw) > 2
                ]
                native_tags = HASHTAG_RE.findall(desc)
                
                out_rows.append({
                    "description": desc,
                    "topics": parsed.get("topics", ["general"]),
                    "keywords": cleaned_kw,
                    "hashtags": native_tags
                })

            # Handle remaining items with fallback
            remaining_count = len(batch) - len(parsed_objs)
            if remaining_count > 0:
                print(f"[TIKTOK ANALYZER] Using fallback for {remaining_count} items")
                for i in range(len(parsed_objs), len(batch)):
                    desc = batch[i]
                    native_tags = HASHTAG_RE.findall(desc)
                    out_rows.append({
                        "description": desc,
                        "topics": ["general"],
                        "keywords": ["content"],
                        "hashtags": native_tags
                    })

            time.sleep(sleep_s)

        except Exception as e:
            print(f"[TIKTOK ANALYZER] DeepSeek API error: {e}")
            # Fallback for failed batch
            for desc in batch:
                native_tags = HASHTAG_RE.findall(desc)
                out_rows.append({
                    "description": desc,
                    "topics": ["general"],
                    "keywords": ["content"],
                    "hashtags": native_tags
                })

    print(f"[TIKTOK ANALYZER] Completed topic extraction: {len(out_rows)} total items")
    return pd.DataFrame(out_rows)

def get_trending_keywords(seed_kw, max_total=5):
    """Get trending keywords from autocomplete APIs"""
    trending = []
    print(f"[TIKTOK ANALYZER] Getting trending keywords for: {seed_kw}")
    
    for kw in seed_kw[:3]:  # Limit to avoid too many requests
        if not kw or len(kw) < 3:  # Skip very short keywords
            continue
            
        print(f"[TIKTOK ANALYZER] 🔍 Autocomplete for: '{kw}'")
        try:
            # Google suggestions
            url = "https://suggestqueries.google.com/complete/search"
            params = {"client": "firefox", "q": kw}
            response = requests.get(url, params=params, timeout=4)
            google_suggestions = response.json()[1] if response.status_code == 200 else []
            
            # YouTube suggestions
            params = {"client": "firefox", "ds": "yt", "q": kw}
            response = requests.get(url, params=params, timeout=4)
            youtube_suggestions = response.json()[1] if response.status_code == 200 else []
            
            all_suggestions = google_suggestions + youtube_suggestions
            
            # Filter suggestions
            for suggestion in all_suggestions[:10]:  # Limit suggestions per keyword
                if (suggestion and 
                    suggestion.lower() != kw.lower() and
                    kw.lower() in suggestion.lower() and
                    "near me" not in suggestion.lower() and
                    len(suggestion.split()) <= 4 and
                    suggestion not in trending):
                    
                    trending.append(suggestion)
                    print(f"[TIKTOK ANALYZER] ✓ Added trending: '{suggestion}'")
                    
                    if len(trending) >= max_total:
                        return trending
                        
        except Exception as e:
            print(f"[TIKTOK ANALYZER] Trending keywords error for {kw}: {e}")
            # Add fallback trending keywords
            fallbacks = [f"{kw} 2024", f"{kw} trend", f"viral {kw}"]
            for fallback in fallbacks:
                if fallback not in trending and len(trending) < max_total:
                    trending.append(fallback)
    
    # If we don't have enough, add some general trending terms
    if len(trending) < 3:
        general_trending = ["viral trend", "fyp", "trending now", "2024 trend", "viral content"]
        for term in general_trending:
            if term not in trending and len(trending) < max_total:
                trending.append(term)
    
    print(f"[TIKTOK ANALYZER] Final trending keywords: {trending}")
    return trending

STOP_WORDS = {
    "the","a","an","and","or","for","of","to","in","with","on","at","by",
    "near","me","my","your","our","this","that","it","is","are","was","were"
}

def distill_core_keywords(analysis_df: pd.DataFrame, n_core: int = 5, min_video_frac: float = 0.15) -> list[str]:
    """Extract core keywords from analysis data"""
    print(f"[TIKTOK ANALYZER] Distilling core keywords from {len(analysis_df)} videos...")
    
    if analysis_df.empty:
        return ["content", "video", "trending"]
    
    num_videos = len(analysis_df)
    min_hits = max(1, math.ceil(num_videos * min_video_frac))
    
    token_hits = defaultdict(set)
    global_occ = Counter()

    for idx, row in analysis_df.iterrows():
        kw = row.get("keywords") if isinstance(row.get("keywords"), list) else []
        topics = row.get("topics") if isinstance(row.get("topics"), list) else []
        hashtags = row.get("hashtags") if isinstance(row.get("hashtags"), list) else []

        all_terms = kw + topics + hashtags
        tokens = set()
        
        for term in all_terms:
            if isinstance(term, str):
                # Extract individual words
                words = re.findall(r"[a-z]+", term.lower())
                tokens.update(words)

        # Filter tokens
        filtered_tokens = {
            t for t in tokens 
            if (t not in STOP_WORDS and 
                not _is_geo_kw(t) and 
                len(t) > 2 and 
                len(t) < 20)
        }

        for token in filtered_tokens:
            token_hits[token].add(idx)
            global_occ[token] += 1

    # Keep tokens that appear in enough videos
    qualified = {tok: hits for tok, hits in token_hits.items() if len(hits) >= min_hits}
    
    print(f"[TIKTOK ANALYZER] Found {len(qualified)} qualified keywords")

    # Rank by frequency and video coverage
    ranked = sorted(
        qualified.items(),
        key=lambda kv: (-len(kv[1]), -global_occ[kv[0]])
    )

    top_tokens = [tok for tok, _ in ranked][:n_core]
    
    # Ensure we have at least some keywords
    if not top_tokens:
        top_tokens = ["content", "video", "social"]
    
    print(f"[TIKTOK ANALYZER] Core keywords: {top_tokens}")
    return top_tokens

def generate_video_ideas(topics: list[str], trending_kw: list[str], n_ideas: int = 10) -> pd.DataFrame:
    """Generate video ideas using DeepSeek API"""
    print(f"[TIKTOK ANALYZER] Generating {n_ideas} video ideas...")
    print(f"[TIKTOK ANALYZER] Topics: {topics}")
    print(f"[TIKTOK ANALYZER] Trending: {trending_kw}")
    
    if not topics:
        topics = ["lifestyle", "entertainment", "trending"]
    if not trending_kw:
        trending_kw = ["viral", "fyp", "trending"]
    
    prompt = f"""Generate {n_ideas} TikTok video ideas in JSON format. Each line should be a separate JSON object.

Channel focuses on: {', '.join(topics[:3])}
Trending keywords to include: {', '.join(trending_kw[:3])}

For each idea, create a JSON with:
- hook: catchy 8-12 word title
- content: one sentence describing what to film
- cta: call-to-action for engagement
- hashtags: array of 3-5 relevant hashtags

Example format:
{{"hook":"Why everyone is obsessed with this trend","content":"Film yourself trying the latest viral challenge","cta":"Comment if you've tried this","hashtags":["fyp","viral","trending"]}}

Generate {n_ideas} unique ideas now:"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            temperature=0.7,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": "You are a viral content strategist. Generate creative TikTok video ideas in valid JSON format, one per line."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.choices[0].message.content
        print(f"[TIKTOK ANALYZER] DeepSeek response length: {len(content)}")
        
        ideas = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or not ('{' in line and '}' in line):
                continue
                
            try:
                # Try to parse the JSON
                idea = json.loads(line)
                
                # Validate required fields
                if all(key in idea for key in ['hook', 'content', 'cta', 'hashtags']):
                    # Ensure hashtags is a list
                    if isinstance(idea['hashtags'], list):
                        ideas.append(idea)
                        print(f"[TIKTOK ANALYZER] ✓ Added idea: {idea['hook']}")
                        
                        if len(ideas) >= n_ideas:
                            break
                            
            except json.JSONDecodeError:
                continue
        
        print(f"[TIKTOK ANALYZER] Successfully generated {len(ideas)} ideas")
        
        # Fill remaining spots with fallback ideas if needed
        while len(ideas) < min(n_ideas, 5):
            topic = topics[len(ideas) % len(topics)] if topics else "trending"
            trending_term = trending_kw[len(ideas) % len(trending_kw)] if trending_kw else "viral"
            
            fallback_idea = {
                "hook": f"This {topic} trend is everywhere right now",
                "content": f"Create content showcasing {topic} with {trending_term} elements",
                "cta": "Drop a comment if you agree",
                "hashtags": ["fyp", "viral", topic.lower().replace(" ", "")]
            }
            ideas.append(fallback_idea)
            print(f"[TIKTOK ANALYZER] ⚠️ Added fallback idea: {fallback_idea['hook']}")

        return pd.DataFrame(ideas)

    except Exception as e:
        print(f"[TIKTOK ANALYZER] Video ideas generation error: {e}")
        
        # Return meaningful fallback ideas
        fallback_ideas = []
        for i in range(min(n_ideas, 5)):
            topic = topics[i % len(topics)] if topics else "content"
            trending_term = trending_kw[i % len(trending_kw)] if trending_kw else "viral"
            
            fallback_ideas.append({
                "hook": f"Why {topic} creators are doing this now",
                "content": f"Film yourself exploring {topic} trends with {trending_term} approach",
                "cta": "Tell me your thoughts in the comments",
                "hashtags": ["fyp", "trending", topic.lower().replace(" ", ""), "viral"]
            })
        
        print(f"[TIKTOK ANALYZER] Using {len(fallback_ideas)} fallback ideas")
        return pd.DataFrame(fallback_ideas)

def calculate_engagement_metrics(df: pd.DataFrame) -> dict:
    """Calculate engagement metrics from video data"""
    if df.empty:
        return {
            "average_engagement_rate": 0,
            "mean_views": 0,
            "num_videos": 0,
            "total_likes": 0,
            "total_comments": 0
        }
    
    # Convert likes and comments to numbers
    df["likes_num"] = df["likes"].apply(_num)
    df["comments_num"] = df["comments"].apply(_num)
    
    # Estimate views (rough calculation)
    df["estimated_views"] = df["likes_num"] * 15  # Slightly higher multiplier
    df["estimated_views"] = df["estimated_views"].replace(0, 1)  # Avoid division by zero
    
    # Calculate engagement rate
    df["engagement_rate"] = ((df["likes_num"] + df["comments_num"]) / df["estimated_views"]) * 100
    df["engagement_rate"] = df["engagement_rate"].fillna(0)
    
    return {
        "average_engagement_rate": df["engagement_rate"].mean(),
        "mean_views": df["estimated_views"].mean(),
        "num_videos": len(df),
        "total_likes": df["likes_num"].sum(),
        "total_comments": df["comments_num"].sum()
    }

def generate_recommendations(metrics: dict, analysis_df: pd.DataFrame) -> list[str]:
    """Generate growth recommendations based on analysis"""
    recommendations = []
    
    if metrics["average_engagement_rate"] < 2:
        recommendations.append("Focus on creating more engaging content - your current rate is below average")
    elif metrics["average_engagement_rate"] < 5:
        recommendations.append("Good engagement! Try interactive content like polls and questions to boost it further")
    else:
        recommendations.append("Excellent engagement rate! Keep doing what you're doing")
    
    if metrics["num_videos"] < 10:
        recommendations.append("Post more consistently - aim for at least 10-15 videos to build momentum")
    
    if not analysis_df.empty:
        # Find most common topics
        all_topics = []
        for topics in analysis_df["topics"]:
            if isinstance(topics, list):
                all_topics.extend(topics)
        
        if all_topics:
            topic_counts = Counter(all_topics)
            if topic_counts:
                top_topic = topic_counts.most_common(1)[0][0]
                recommendations.append(f"Double down on '{top_topic}' content - it's your strongest theme")
    
    recommendations.extend([
        "Post during peak hours (6-9 PM) for maximum visibility",
        "Use 3-5 trending hashtags relevant to your niche",
        "Respond to comments within the first 2 hours of posting"
    ])
    
    return recommendations[:6]  # Return up to 6 recommendations

def run_analysis(username: str) -> dict:
    """Main analysis function called by Flask app"""
    try:
        print(f"[TIKTOK ANALYZER] Starting comprehensive analysis for @{username}")
        
        # Load CSV file created by scraper
        csv_filename = f"{username}_tiktok_videos.csv"
        
        if not os.path.exists(csv_filename):
            return {"error": f"CSV file {csv_filename} not found. Run scraper first."}
        
        df = pd.read_csv(csv_filename)
        
        if df.empty:
            return {"error": "No video data found in CSV file."}
        
        print(f"[TIKTOK ANALYZER] Loaded {len(df)} videos for analysis")
        
        # Extract topics and keywords using DeepSeek
        descriptions = df["description"].dropna().tolist()
        if not descriptions:
            return {"error": "No valid descriptions found in video data."}
        
        print("[TIKTOK ANALYZER] 🤖 Extracting topics and keywords with DeepSeek AI...")
        analysis_df = extract_topics_keywords(descriptions)
        
        # Get core keywords and trending terms
        print("[TIKTOK ANALYZER] 🔍 Distilling core keywords...")
        core_kw = distill_core_keywords(analysis_df, n_core=5)
        
        print("[TIKTOK ANALYZER] 📈 Fetching trending keywords...")
        trending_kw = get_trending_keywords(core_kw, max_total=5)
        
        # Calculate metrics
        print("[TIKTOK ANALYZER] 📊 Calculating engagement metrics...")
        metrics = calculate_engagement_metrics(df)
        
        # Generate recommendations
        print("[TIKTOK ANALYZER] 💡 Generating recommendations...")
        recommendations = generate_recommendations(metrics, analysis_df)
        
        # Generate content ideas
        print("[TIKTOK ANALYZER] 🎬 Generating content ideas with DeepSeek AI...")
        agg_topics = []
        for topics in analysis_df["topics"]:
            if isinstance(topics, list):
                agg_topics.extend(topics)
        
        # Get top topics, ensuring we have some
        if agg_topics:
            top_topics = [item for item, count in Counter(agg_topics).most_common(5)]
        else:
            top_topics = ["lifestyle", "entertainment", "trending"]
            
        print(f"[TIKTOK ANALYZER] Top topics for content generation: {top_topics}")
        ideas_df = generate_video_ideas(top_topics, trending_kw, n_ideas=8)
        
        # Find top and bottom performing clips
        df_sorted = df.copy()
        df_sorted["total_engagement"] = df_sorted["likes"].apply(_num) + df_sorted["comments"].apply(_num)
        df_sorted = df_sorted.sort_values("total_engagement", ascending=False)
        
        top_clips = df_sorted.head(3)[["description", "likes", "comments"]].to_dict("records")
        bottom_clips = df_sorted.tail(3)[["description", "likes", "comments"]].to_dict("records")
        
        print(f"[TIKTOK ANALYZER] ✅ Analysis complete!")
        print(f"[TIKTOK ANALYZER] - Core keywords: {len(core_kw)}")
        print(f"[TIKTOK ANALYZER] - Trending terms: {len(trending_kw)}")
        print(f"[TIKTOK ANALYZER] - Content ideas: {len(ideas_df)}")
        print(f"[TIKTOK ANALYZER] - Recommendations: {len(recommendations)}")
        
        return {
            "average_engagement_rate": round(metrics["average_engagement_rate"], 2),
            "mean_views": int(metrics["mean_views"]),
            "num_videos": metrics["num_videos"],
            "recommendations": recommendations,
            "plan": ideas_df.to_dict("records"),
            "top_clips": top_clips,
            "bottom_clips": bottom_clips,
            "core_keywords": core_kw,
            "trending_keywords": trending_kw
        }
        
    except Exception as e:
        print(f"[TIKTOK ANALYZER] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"Analysis failed: {str(e)}"}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        username = sys.argv[1]
        result = run_analysis(username)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python analyzer.py <username>")