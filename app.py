from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from trend_agent import run_trend_agent  # Your existing module
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

app = Flask(__name__)
CORS(app) 

# MongoDB setup
client = MongoClient("mongodb+srv://mariamma:0dkg0bIoBxIlDIww@cluster0.yw4vtrc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # 🔁 Update with your connection string
db = client["trend_db"]                             # 🔁 Your DB name
collection = db["aiagent"]                          # 🔁 Your collection name

@app.before_request
def global_auth_check():
    exempt_routes = ['default']
    if request.endpoint in exempt_routes:
        return
    if request.method == "OPTIONS":
        return '', 200

def format_email_body(summaries):
    blocks = []
    for item in summaries:
        blocks.append(f"📌 *{item.heading}*\n{item.summary}\n🔸 Engagement: {item.engagement or 'N/A'}\n")
    return "\n\n".join(blocks)

def send_email(subject, body, to_email):
    sender_email = "sandeep.pesala@gmail.com"
    sender_password = "yirb srxq xied vdip"  # Use App Password, not your real Gmail password

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    intro = "Please find the competitor trends below:\n\n"
    full_body = intro + body
    msg.attach(MIMEText(full_body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)
        print("✅ Email sent")

def refresh_trends_task():
    all_records = list(collection.find())
    for record in all_records:
        brand = record.get("brand")
        product = record.get("product")
        subject = record.get("email_subject", f"{brand} - Trend Summary")
        email_id = record.get("email_id")
        metadata = record.get("metadata", {})

        if not brand or not product or not email_id:
            continue  # Skip if essential data is missing

        # Run trend agent
        trend_output = run_trend_agent(f"What are {brand}'s competitors doing in the {product} space?", brand, product)
        summaries = trend_output.get("summaries", [])

        # Format summary
        email_body = format_email_body(summaries)
        timestamp = datetime.now().isoformat()

        # Update only email_body
        collection.update_one(
            {"id": trend_id},
            {"$set": {
                "email_body": email_body,
                "updated_at": timestamp
            }}
        )

        # Send email
        send_email(subject, email_body, email_id)

    print("✅ All trends refreshed and emails sent.")

@app.route("/refresh-trends", methods=["GET","OPTIONS"])
def trigger_refresh_async():
    thread = threading.Thread(target=refresh_trends_task)
    thread.start()
    return jsonify({"status": "success", "message": "⏳ Refresh started in background."}), 202

@app.route('/trend-summary', methods=['POST', 'OPTIONS'])
def summary():
    try:
        data = request.get_json(force=True)

        # Extract fields
        
        brand = data.get("brand")
        product = data.get("product")
        subject = data.get("email_subject", f"{brand} - Trend Summary")
        email_id = data.get("email_id")
        name = data.get("name")
        metadata = data.get("metadata", {})
        
        # Identify missing fields
        missing_fields = []
        if not brand:
            missing_fields.append("brand")
        if not product:
            missing_fields.append("product")
        if not email_id:
            missing_fields.append("email_id")
        if not name:
            missing_fields.append("name")
        
        # Return error if any required field is missing
        if missing_fields:
            return jsonify({
                "status": "error",
                "message": f"Missing required field(s): {', '.join(missing_fields)}"
            }), 400
        existing = collection.find_one({"email_id":email_id,"product":product,"brand":brand})
        if existing:
            return jsonify({
                "status": "error",
                "message": "Trend filters already exists"
            }), 400
        thread = threading.Thread(target=trend_summary, args=(data,))
        thread.start()
        return jsonify({"status": "success", "message": "⏳ Email will be sent shortly"}), 202
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def trend_summary(data):
    try:
        brand = data.get("brand")
        product = data.get("product")
        subject = data.get("email_subject", f"{brand} - Trend Summary")
        email_id = data.get("email_id")
        name = data.get("name")
        metadata = data.get("metadata", {})

        if not trend_id or not brand or not product or not email_id or not name:
            print("❌ Missing required fields")
            return

        query = f"What are {brand}'s competitors doing in the {product} space?"

        # Run trend agent
        trend_output = run_trend_agent(query, brand, product)
        summaries = trend_output.get("summaries", [])

        # Format summary
        email_body = format_email_body(summaries)
        timestamp = datetime.now().isoformat()
        send_email(subject, email_body, email_id)

        collection.insert_one({
            "id": trend_id,
            "brand": brand,
            "product": product,
            "email_id": email_id,
            "name": name,
            "email_subject": subject,
            "email_body": email_body,
            "metadata": metadata,
            "created_at": timestamp,
            "updated_at": timestamp
        })
        print(f"✅ Trend {trend_id} inserted.")

    except Exception as e:
        print(f"❌ Error processing trend summary: {str(e)}")

@app.route("/")
def default():
    return jsonify({"status":"success","message":"API is working"}),200

if __name__ == "__main__":
    app.run(debug=True)
