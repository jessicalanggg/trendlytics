import os, json, time, re, textwrap
import pandas as pd
from openai import OpenAI
from pathlib import Path

class YouTubeChannelAnalyzer:
    def __init__(self, api_key=None):
        """Initialize the analyzer with DeepSeek API key."""
        # Use provided API key, fallback to environment variable, then hardcoded key
        if api_key:
            self.api_key = api_key
        elif "DEEPSEEK_API_KEY" in os.environ:
            self.api_key = os.environ["DEEPSEEK_API_KEY"]
        else:
            # Hardcoded API key - matches your original
            self.api_key = "sk-90b8397488ed4726a77af9f4b0da34f4"
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        
    def load_video_data(self, csv_path):
        """Load video data from CSV file (schema-agnostic)."""
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
            
        try:
            df = pd.read_csv(csv_path, on_bad_lines="skip", engine="python")
            
            # Clean up any whitespace in column names
            df.columns = df.columns.str.strip()
            text_cols = [c for c in df.columns if df[c].dtype == object]
            
            # Try to find title column with various possible names
            title_candidates = ['title', 'Title', 'video_title', 'name', 'Name', 'description', 'Description']
            titles = []
            
            for candidate in title_candidates:
                if candidate in df.columns:
                    # Get titles and clean them
                    raw_titles = df[candidate].astype(str).dropna()
                    titles = [t.strip() for t in raw_titles if t.strip() and t.strip().lower() not in ['nan', 'none', 'null']]
                    print(f"✔️ Using '{candidate}' column for video titles")
                    break
            
            # If no specific title column found, use first text column
            if not titles and text_cols:
                raw_titles = df[text_cols[0]].astype(str).dropna()
                titles = [t.strip() for t in raw_titles if t.strip() and t.strip().lower() not in ['nan', 'none', 'null']]
                print(f"✔️ Using '{text_cols[0]}' column for video titles")
            
            if not titles:
                raise ValueError("No text columns found in CSV or all text columns are empty")
                
            # Filter out very short or non-meaningful titles
            valid_titles = []
            for title in titles:
                # Remove common extraction artifacts
                cleaned_title = re.sub(r'^Video \d+\s*\(extraction failed\)', '', title).strip()
                if len(cleaned_title) > 5 and cleaned_title.lower() not in ['untitled video', 'sample video', 'video']:
                    valid_titles.append(cleaned_title)
            
            if not valid_titles:
                # If all titles are filtered out, use the original ones but log a warning
                print("⚠️ All titles appear to be generic/placeholder - using original titles")
                valid_titles = [t for t in titles if len(t.strip()) > 3]
                
            if not valid_titles:
                raise ValueError("No valid video titles found in the data")
                
            print(f"✔️ Loaded {len(valid_titles)} valid video titles from {csv_path}")
            return df, valid_titles
            
        except Exception as e:
            raise RuntimeError(f"Error loading CSV: {str(e)}")

    def _parse_json(self, txt):
        """Parse JSON from API response, handling code blocks."""
        txt = re.sub(r"^```(?:json)?\s*|```$", "", txt.strip(), flags=re.DOTALL).strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No valid JSON object found")
        return json.loads(txt[start:end+1])

    def extract_channel_signature(self, video_titles, max_titles=50):
        """Extract channel vibes, topics, and keywords from video titles."""
        # Limit titles to avoid token limits
        sample_titles = video_titles[:max_titles] if len(video_titles) > max_titles else video_titles
        
        base_prompt = textwrap.dedent(f"""
            You are an elite YouTube content analyst.
            Analyze these video titles and extract the channel's signature elements.
            
            Video titles: {json.dumps(sample_titles[:30], indent=2)}
            
            Return ONLY valid JSON with these exact keys:
            - "vibes": 3-5 descriptive words about the channel's personality/style
            - "topics": 5-8 main subject areas the channel covers
            - "keywords": 8-12 important terms that define the channel's niche
            
            Example format:
            {{
                "vibes": ["educational", "entertaining", "accessible"],
                "topics": ["science", "physics", "experiments"],
                "keywords": ["research", "discovery", "explanation"]
            }}
        """).strip()
        
        for attempt in range(3):
            try:
                print(f"[YOUTUBE ANALYZER] Extracting channel signature (attempt {attempt + 1})...")
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a YouTube analytics expert. Return exactly one JSON object and nothing else."},
                        {"role": "user", "content": base_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
                result = self._parse_json(resp.choices[0].message.content)
                
                # Validate required keys
                required_keys = ["vibes", "topics", "keywords"]
                if all(key in result for key in required_keys):
                    print(f"[YOUTUBE ANALYZER] ✔️ Successfully extracted channel signature")
                    return result
                else:
                    print(f"[YOUTUBE ANALYZER] ⚠️ Missing keys in attempt {attempt + 1}, retrying...")
                    
            except Exception as e:
                print(f"[YOUTUBE ANALYZER] ⚠️ Attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:
                    # Return fallback signature
                    print(f"[YOUTUBE ANALYZER] Using fallback signature")
                    return {
                        "vibes": ["creative", "engaging", "informative"],
                        "topics": ["entertainment", "lifestyle", "trending"],
                        "keywords": ["content", "video", "youtube", "creator"]
                    }
                time.sleep(1)

    def generate_video_ideas(self, topics, vibes, n=10):
        """Generate video topic ideas based on channel signature."""
        prompt = f"""
You are a creative strategist for a YouTube channel with these characteristics:
VIBES: {', '.join(vibes)}
TOPICS: {', '.join(topics)}

Generate {n} specific, actionable video topic ideas that:
1. Align with the channel's established topics and style
2. Are practical to film and produce
3. Have strong viewer appeal potential
4. Are 5-15 words each

Format as a simple bulleted list with no extra commentary.
        """.strip()
        
        try:
            print(f"[YOUTUBE ANALYZER] Generating {n} video ideas...")
            resp = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=800
            )
            
            content = resp.choices[0].message.content.strip()
            ideas = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    # Clean up bullet points
                    clean_line = re.sub(r"^[\d\.\-•*\s]+", "• ", line).strip()
                    if clean_line != "•" and len(clean_line) > 3:
                        ideas.append(clean_line)
            
            print(f"[YOUTUBE ANALYZER] ✔️ Generated {len(ideas)} video ideas")
            return ideas[:n]
            
        except Exception as e:
            print(f"[YOUTUBE ANALYZER] ⚠️ Error generating video ideas: {str(e)}")
            # Return fallback ideas based on topics
            fallback_ideas = []
            for i, topic in enumerate(topics[:5]):
                fallback_ideas.append(f"• How to master {topic} in 2025")
                fallback_ideas.append(f"• {topic} tips everyone should know")
            return fallback_ideas[:n]

    def generate_growth_tips(self, topics, vibes, steps=5):
        """Generate actionable growth tips for the channel."""
        prompt = f"""
You are a senior YouTube growth consultant with proven track record.

Channel Profile:
- TOPICS: {', '.join(topics)}
- VIBES: {', '.join(vibes)}

Provide {steps} specific, actionable growth strategies that are:
1. Tailored to this channel's niche and style
2. Implementable within 30 days
3. Based on current YouTube best practices
4. 25 words or less each

Format as bulleted list, no fluff or explanations.
        """.strip()
        
        try:
            print(f"[YOUTUBE ANALYZER] Generating {steps} growth tips...")
            resp = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=600
            )
            
            content = resp.choices[0].message.content.strip()
            tips = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    clean_line = re.sub(r"^[\d\.\-•*\s]+", "• ", line).strip()
                    if clean_line != "•" and len(clean_line) > 3:
                        tips.append(clean_line)
            
            print(f"[YOUTUBE ANALYZER] ✔️ Generated {len(tips)} growth tips")
            return tips[:steps]
            
        except Exception as e:
            print(f"[YOUTUBE ANALYZER] ⚠️ Error generating growth tips: {str(e)}")
            # Return fallback tips
            return [
                "• Optimize thumbnails with bold text and bright colors",
                "• Upload consistently on the same days each week", 
                "• Engage with comments within first 2 hours of posting",
                "• Create series or playlists around your main topics",
                "• Collaborate with creators in similar niches"
            ]

def run_youtube_analysis(csv_path):
    """Main analysis function called by Flask app or scraper"""
    try:
        print(f"[YOUTUBE ANALYZER] Starting comprehensive analysis for CSV: {csv_path}")
        
        if not os.path.exists(csv_path):
            return {"error": f"CSV file {csv_path} not found."}
        
        # Initialize analyzer
        analyzer = YouTubeChannelAnalyzer()
        
        # Load and validate data
        print("[YOUTUBE ANALYZER] 📁 Loading video data...")
        df, titles = analyzer.load_video_data(csv_path)
        
        if not titles:
            return {"error": "No valid video titles found in CSV file."}
        
        print(f"[YOUTUBE ANALYZER] Loaded {len(titles)} video titles for analysis")
        
        # Extract channel signature
        print("[YOUTUBE ANALYZER] 🎭 Extracting channel signature...")
        channel_sig = analyzer.extract_channel_signature(titles)
        
        # Generate video ideas
        print("[YOUTUBE ANALYZER] 🎬 Generating video ideas...")
        video_ideas = analyzer.generate_video_ideas(
            channel_sig["topics"], 
            channel_sig["vibes"],
            n=10
        )
        
        # Generate growth tips
        print("[YOUTUBE ANALYZER] 🚀 Generating growth tips...")
        growth_tips = analyzer.generate_growth_tips(
            channel_sig["topics"], 
            channel_sig["vibes"],
            steps=6
        )
        
        print(f"[YOUTUBE ANALYZER] ✅ Analysis complete!")
        print(f"[YOUTUBE ANALYZER] - Channel vibes: {len(channel_sig['vibes'])}")
        print(f"[YOUTUBE ANALYZER] - Topics: {len(channel_sig['topics'])}")
        print(f"[YOUTUBE ANALYZER] - Keywords: {len(channel_sig['keywords'])}")
        print(f"[YOUTUBE ANALYZER] - Video ideas: {len(video_ideas)}")
        print(f"[YOUTUBE ANALYZER] - Growth tips: {len(growth_tips)}")
        
        return {
            "signature": channel_sig,
            "video_ideas": video_ideas,
            "growth_tips": growth_tips,
            "video_count": len(titles),
            "csv_file": os.path.basename(csv_path)
        }
        
    except Exception as e:
        print(f"[YOUTUBE ANALYZER] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"YouTube analysis failed: {str(e)}"}

def analyze_from_scraper_result(scraper_result):
    """Analyze data directly from scraper result object - enhanced integration"""
    try:
        csv_path = scraper_result.get("csv_path")
        if not csv_path:
            return {"error": "No CSV path provided in scraper result"}
        
        print(f"[YOUTUBE ANALYZER] Analyzing data from scraper result...")
        analysis_result = run_youtube_analysis(csv_path)
        
        if "error" in analysis_result:
            return analysis_result
        
        # Enhance with scraper data
        enhanced_result = {
            "status": "success",
            "message": f"Complete analysis for {scraper_result.get('channel_name', 'channel')}",
            "channel_info": {
                "channel_id": scraper_result.get("channel_id", "N/A"),
                "channel_name": scraper_result.get("channel_name", "N/A"),
                "subscribers": scraper_result.get("subscribers", "N/A"),
                "video_count": scraper_result.get("video_count", 0)
            },
            "signature": analysis_result.get("signature", {}),
            "video_ideas": analysis_result.get("video_ideas", []),
            "growth_tips": analysis_result.get("growth_tips", []),
            "csv_file": scraper_result.get("csv_file"),
            "analysis_metadata": {
                "analyzed_videos": analysis_result.get("video_count", 0),
                "csv_source": analysis_result.get("csv_file")
            }
        }
        
        return enhanced_result
        
    except Exception as e:
        return {"error": f"Failed to analyze scraper result: {str(e)}"}

def full_channel_analysis(channel_id):
    """Complete end-to-end analysis - scrape + analyze in one function"""
    try:
        print(f"[YOUTUBE ANALYZER] Starting full channel analysis for: {channel_id}")
        
        # Import and run scraper
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("scraper_yt", "scraper-yt.py")
            scraper_yt = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scraper_yt)
            scrape_youtube_channel = scraper_yt.scrape_youtube_channel
        except ImportError:
            return {"error": "YouTube scraper not available. Please ensure scraper-yt.py is in the current directory."}
        
        # Step 1: Scrape
        print("[YOUTUBE ANALYZER] Step 1: Scraping channel data...")
        scrape_result = scrape_youtube_channel(channel_id)
        
        if "error" in scrape_result:
            return {"error": f"Scraping failed: {scrape_result['error']}"}
        
        # Step 2: Analyze
        print("[YOUTUBE ANALYZER] Step 2: Analyzing scraped data...")
        analysis_result = analyze_from_scraper_result(scrape_result)
        
        return analysis_result
        
    except Exception as e:
        return {"error": f"Full analysis failed: {str(e)}"}

# Keep the original class-based interface for backward compatibility
def analyze_channel(csv_path, image_path=None):
    """Legacy function for backward compatibility"""
    analyzer = YouTubeChannelAnalyzer()
    
    print("🚀 Starting YouTube Channel Analysis...")
    
    # Load data
    df, titles = analyzer.load_video_data(csv_path)
    
    # Extract channel signature
    print("\n🔍 Analyzing channel signature...")
    channel_sig = analyzer.extract_channel_signature(titles)
    
    print(f"✔️ Channel Vibes: {', '.join(channel_sig['vibes'])}")
    print(f"✔️ Main Topics: {', '.join(channel_sig['topics'])}")
    print(f"✔️ Key Keywords: {', '.join(channel_sig['keywords'])}")
    
    # Generate video ideas
    print("\n🎬 Generating Video Topic Ideas...")
    video_ideas = analyzer.generate_video_ideas(
        channel_sig["topics"], 
        channel_sig["vibes"]
    )
    print("\nActionable Video Topics:")
    for idea in video_ideas:
        print(idea)
    
    # Generate growth tips
    print("\n🚀 Generating Growth Tips...")
    growth_tips = analyzer.generate_growth_tips(
        channel_sig["topics"], 
        channel_sig["vibes"]
    )
    print("\nGrowth Strategies:")
    for tip in growth_tips:
        print(tip)
    
    return {
        'signature': channel_sig,
        'video_ideas': video_ideas,
        'growth_tips': growth_tips,
        'data': df
    }

# Usage Example
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        input_arg = sys.argv[1]
        
        if input_arg.endswith('.csv'):
            # Direct CSV analysis
            print(f"🎯 Analyzing CSV file: {input_arg}")
            result = run_youtube_analysis(input_arg)
            if "error" in result:
                print(f"❌ Analysis failed: {result['error']}")
            else:
                print("✅ Analysis completed successfully!")
                print(json.dumps(result, indent=2))
        else:
            # Assume it's a channel ID - do full analysis
            print(f"🎯 Running full analysis for channel: {input_arg}")
            result = full_channel_analysis(input_arg)
            
            if "error" in result:
                print(f"❌ Analysis failed: {result['error']}")
            else:
                print("✅ Full analysis completed successfully!")
                
                # Display results nicely
                if "channel_info" in result:
                    info = result["channel_info"]
                    print(f"\n📺 Channel: {info.get('channel_name', 'N/A')} (@{info.get('channel_id')})")
                    print(f"👥 Subscribers: {info.get('subscribers', 'N/A')}")
                    print(f"📹 Videos Analyzed: {info.get('video_count', 0)}")
                
                if "signature" in result:
                    sig = result["signature"]
                    print(f"\n🎭 Channel Vibes: {', '.join(sig.get('vibes', []))}")
                    print(f"📚 Topics: {', '.join(sig.get('topics', []))}")
                    print(f"🔑 Keywords: {', '.join(sig.get('keywords', []))}")
                
                if "video_ideas" in result:
                    print(f"\n🎬 Video Ideas:")
                    for idea in result["video_ideas"]:
                        print(f"   {idea}")
                
                if "growth_tips" in result:
                    print(f"\n🚀 Growth Tips:")
                    for tip in result["growth_tips"]:
                        print(f"   {tip}")
    else:
        # Default example - look for existing CSV files
        csv_files = [f for f in os.listdir('.') if f.endswith('_youtube_videos.csv')]
        
        if csv_files:
            csv_path = csv_files[0]  # Use the first found CSV
            print(f"🎯 Found existing CSV: {csv_path}")
            
            try:
                results = analyze_channel(csv_path)
                print("\n✅ Analysis Complete!")
            except Exception as e:
                print(f"❌ Analysis failed: {str(e)}")
        else:
            print("❌ No YouTube CSV files found in current directory")
            print("💡 Usage:")
            print("  python youtubeanalyzer.py <csv_file_path>     # Analyze existing CSV")
            print("  python youtubeanalyzer.py <channel_id>       # Full analysis (scrape + analyze)")
            print("  or run scraper first: python scraper-yt.py <channel_id>")