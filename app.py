from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from trend_agent import run_trend_agent  # Your existing module
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app) 

# MongoDB setup
client = MongoClient("mongodb+srv://mariamma:0dkg0bIoBxIlDIww@cluster0.yw4vtrc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # 🔁 Update with your connection string
db = client["trend_db"]                             # 🔁 Your DB name
collection = db["aiagent"]                          # 🔁 Your collection name

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
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)
        print("✅ Email sent")



@app.route('/trend-summary', methods=['POST'])
def trend_summary():
    try:
        data = request.get_json(force=True)

        trend_id = data.get("id")
        brand = data.get("brand")
        product = data.get("product")
        subject = data.get("email_subject", f"{brand} - Trend Summary")
        email_id = data.get("email_id")
        name = data.get("name")
        metadata = data.get("metadata", {})

        if not trend_id or not brand or not product:
            return jsonify({"status": "error", "message": "Missing 'id', 'brand','email_id','name' or 'product'."}), 400

        # Build query
        query = f"What are {brand}'s competitors doing in the {product} space?"

        # Run trend agent
        trend_output = run_trend_agent(query,brand,product)
        summaries = trend_output.get("summaries", [])

        # Format summary
        email_body = format_email_body(summaries)
        timestamp = datetime.now().isoformat()
        send_email(subject, email_body, email_id)

        # Check if trend already exists
        existing = collection.find_one({"id": trend_id})

        if existing:
            # Update document
            collection.update_one(
                {"id": trend_id},
                {"$set": {
                    "email_subject": subject,
                    "email_body": email_body,
                    "brand": brand,
                    "product": product,
                    "metadata": metadata,
                    "updated_at": timestamp
                }}
            )
            action = "updated"
        else:
            # Insert new document
            collection.insert_one({
                "id": trend_id,
                "brand": brand,
                "product": product,
                "email_id":email_id,
                "name":name,
                "email_subject": subject,
                "email_body": email_body,
                "metadata": metadata,
                "created_at": timestamp,
                "updated_at": timestamp
            })
            action = "inserted"

        return jsonify({"status": "success", "message": f"Trend {action} successfully", "id": trend_id}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"❌ Error: {str(e)}"}), 500

@app.route("/")
def default():
    return jsonify({"status":"success","message":"API is working"}),200

if __name__ == "__main__":
    app.run(debug=True)
