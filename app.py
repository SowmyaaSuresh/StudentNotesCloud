from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import os
from dotenv import load_dotenv
from supabase import create_client
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)
app = Flask(__name__)
@app.route("/")
def home():
    os.makedirs("uploads", exist_ok=True)
    notes = os.listdir("uploads")
    return render_template("index.html", notes=notes)
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return redirect(url_for("home"))
    file.save("uploads/" + file.filename)
    return redirect(url_for("home"))
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("uploads", filename)
@app.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    file_path = os.path.join("uploads", filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    return redirect(url_for("home"))
if __name__ == "__main__":
    app.run(debug=True)