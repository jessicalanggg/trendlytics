import os
import logging
import traceback
from flask import Flask, request, jsonify, render_template, send_from_directory

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Create Flask app with templates folder
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/", methods=["GET"])
def index():
    """Serve the main HTML page"""
    logger.info(f"BASE_DIR = {BASE_DIR}")
    logger.info(f"Files in BASE_DIR: {os.listdir(BASE_DIR)}")
    
    # Try multiple locations for index.html
    possible_locations = [
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(BASE_DIR, "templates", "index.html"),
        os.path.join(BASE_DIR, "static", "index.html")
    ]
    
    for location in possible_locations:
        if os.path.exists(location):
            logger.info(f"Found index.html at: {location}")
            if "templates" in location:
                return render_template("index.html")
            else:
                return send_from_directory(os.path.dirname(location), "index.html")
    
    # Return fallback if no index.html found
    return """
    <h1>Social Media Analytics Hub</h1>
    <p>Frontend not found. Make sure index.html is in the correct location.</p>
    <p>API is running correctly!</p>
    """

@app.route("/scrape", methods=["POST"])
@app.route("/api/tiktok/analyze", methods=["POST"])
def scrape():
    """Handle TikTok scraping requests"""
    try:
        # Get username from both JSON and form data
        if request.is_json:
            data = request.get_json()
            username = data.get("username", "").strip().lstrip("@")
        else:
            username = request.form.get("username", "").strip().lstrip("@")
        
        if not username:
            return jsonify({
                "status": "error", 
                "message": "Username cannot be empty."
            })

        logger.info(f"Starting TikTok scrape for username: {username}")

        # Import here to avoid import errors on startup
        try:
            from scraper import scrape_tiktok
            from analyzer import run_analysis
        except ImportError as e:
            logger.error(f"Import error: {e}")
            return jsonify({
                "status": "error",
                "message": f"Missing dependencies: {str(e)}. Please install: pip install -r requirements.txt"
            })

        # Run scraper
        logger.info("Running TikTok scraper...")
        profile_stats = scrape_tiktok(username)
        
        if "error" in profile_stats:
            return jsonify({
                "status": "error", 
                "message": profile_stats["error"]
            })

        # Run analysis
        logger.info("Running TikTok analysis...")
        analysis = run_analysis(username)
        
        if "error" in analysis:
            return jsonify({
                "status": "error", 
                "message": analysis["error"]
            })

        # Prepare successful response with proper structure
        response_data = {
            "status": "success",
            "message": f"TikTok data for @{username} analyzed successfully!",
            "stats": {
                "username": username,
                "name": profile_stats.get("name", "N/A"),
                "followers": profile_stats.get("followers", "N/A"),
                "following": profile_stats.get("following", "N/A"),
                "total_likes": profile_stats.get("total_likes", "N/A"),
                "engagement": profile_stats.get("engagement_rate", "N/A"),
            },
            "metrics": {
                "avg_engagement": analysis.get("average_engagement_rate", 0),
                "mean_views": analysis.get("mean_views", 0),
                "num_videos": analysis.get("num_videos", 0),
            },
            "recommendations": analysis.get("recommendations", []),
            "content_plan": analysis.get("plan", []),
            "top_clips": analysis.get("top_clips", []),
            "bottom_clips": analysis.get("bottom_clips", []),
            "core_keywords": analysis.get("core_keywords", []),
            "trending_keywords": analysis.get("trending_keywords", [])
        }

        logger.info("TikTok analysis completed successfully")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"TikTok scrape endpoint error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        })

@app.route("/scrape_youtube", methods=["POST"])
def scrape_youtube():
    """Handle YouTube scraping requests"""
    try:
        # Get channel ID from JSON data
        if request.is_json:
            data = request.get_json()
            channel_id = data.get("channel_id", "").strip()
        else:
            channel_id = request.form.get("channel_id", "").strip()
        
        if not channel_id:
            return jsonify({
                "status": "error", 
                "message": "Channel ID cannot be empty."
            })

        logger.info(f"Starting YouTube scrape for channel: {channel_id}")

        # Import here to avoid import errors on startup
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("scraper_yt", "scraper_yt.py")
            scraper_yt = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scraper_yt)
            get_youtube_channel_stats = scraper_yt.get_youtube_channel_stats
        except ImportError as e:
            logger.error(f"Import error: {e}")
            return jsonify({
                "status": "error",
                "message": f"Missing YouTube scraper dependencies: {str(e)}"
            })

        # Run YouTube scraper
        logger.info("Running YouTube scraper...")
        try:
            result = get_youtube_channel_stats(channel_id)
            
            if result and "error" in result:
                return jsonify({
                    "status": "error", 
                    "message": result["error"]
                })

            # Check if CSV was created
            csv_filename = f"{channel_id}_youtube_videos.csv"
            if os.path.exists(csv_filename):
                # Count videos in CSV
                import pandas as pd
                df = pd.read_csv(csv_filename)
                video_count = len(df)
                
                response_data = {
                    "status": "success",
                    "message": f"YouTube channel @{channel_id} scraped successfully!",
                    "channel_id": channel_id,
                    "video_count": video_count,
                    "csv_file": csv_filename
                }
            else:
                response_data = {
                    "status": "error",
                    "message": "Scraping completed but CSV file was not created."
                }

            logger.info("YouTube scraping completed successfully")
            return jsonify(response_data)
            
        except Exception as scrape_error:
            logger.error(f"YouTube scraping failed: {str(scrape_error)}")
            return jsonify({
                "status": "error",
                "message": f"YouTube scraping failed: {str(scrape_error)}"
            })

    except Exception as e:
        logger.error(f"YouTube scrape endpoint error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        })

@app.route("/analyze_youtube", methods=["POST"])
@app.route("/api/youtube/analyze", methods=["POST"])
def analyze_youtube():
    """Handle YouTube analysis requests"""
    try:
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            return jsonify({
                "status": "error",
                "message": "No CSV file uploaded."
            })
        
        file = request.files['csv_file']
        if file.filename == '':
            return jsonify({
                "status": "error",
                "message": "No file selected."
            })
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({
                "status": "error",
                "message": "Please upload a CSV file."
            })

        logger.info(f"Starting YouTube analysis for file: {file.filename}")

        # Import YouTube analyzer
        try:
            from youtubeanalyzer import run_youtube_analysis
        except ImportError as e:
            logger.error(f"YouTube analyzer import error: {e}")
            return jsonify({
                "status": "error",
                "message": f"YouTube analyzer not available: {str(e)}"
            })

        # Save uploaded file temporarily
        temp_csv_path = os.path.join(BASE_DIR, f"temp_{file.filename}")
        file.save(temp_csv_path)
        
        try:
            # Run YouTube analysis
            logger.info("Running YouTube analysis...")
            analysis_result = run_youtube_analysis(temp_csv_path)
            
            if "error" in analysis_result:
                return jsonify({
                    "status": "error",
                    "message": analysis_result["error"]
                })

            response_data = {
                "status": "success",
                "message": f"YouTube channel analysis completed successfully!",
                "signature": analysis_result.get("signature", {}),
                "video_ideas": analysis_result.get("video_ideas", []),
                "growth_tips": analysis_result.get("growth_tips", []),
                "video_count": analysis_result.get("video_count", 0)
            }

            logger.info("YouTube analysis completed successfully")
            return jsonify(response_data)
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)

    except Exception as e:
        logger.error(f"YouTube analysis endpoint error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        })

@app.route("/api/youtube/full", methods=["POST"])
def full_youtube_analysis():
    """Complete YouTube workflow - scrape + analyze in one endpoint"""
    try:
        if request.is_json:
            data = request.get_json()
            channel_id = data.get("channel_id", "").strip().replace('@', '')
        else:
            channel_id = request.form.get("channel_id", "").strip().replace('@', '')
        
        if not channel_id:
            return jsonify({"status": "error", "message": "Channel ID cannot be empty."})

        logger.info(f"Starting full YouTube analysis for channel: {channel_id}")

        # Import and run the complete workflow
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("scraper_yt", "scraper_yt.py")
            scraper_yt = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scraper_yt)
            
            result = scraper_yt.scrape_and_analyze(channel_id)
            
            if "error" in result:
                return jsonify({"status": "error", "message": result["error"]})
            
            logger.info("Full YouTube analysis completed successfully")
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"status": "error", "message": f"Analysis failed: {str(e)}"})

    except Exception as e:
        logger.error(f"Endpoint error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"})

@app.route("/health", methods=["GET"])
@app.route("/api/status", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Social Media Analytics Hub is running"})

@app.errorhandler(404)
def not_found(error):
    logger.error(f"404 error: {request.url}")
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "True").lower() == "true"
    
    logger.info(f"Starting Social Media Analytics Hub on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    # Check for required files
    required_files = ["scraper.py", "analyzer.py", "youtubeanalyzer.py", "scraper_yt.py"]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        logger.warning(f"Missing files: {missing_files}")
    else:
        logger.info("✅ All required files found")
    
    logger.info("🌐 Available endpoints:")
    logger.info("  GET  / - Frontend")
    logger.info("  POST /api/tiktok/analyze - TikTok analysis")
    logger.info("  POST /api/youtube/full - Complete YouTube workflow")
    logger.info("  POST /api/youtube/analyze - YouTube CSV analysis")
    logger.info("  GET  /api/status - Health check")
    
    app.run(debug=debug, host="0.0.0.0", port=port)