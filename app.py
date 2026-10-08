from flask import Flask, render_template, request, redirect, url_for, flash, session
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

# --------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

env_path = Path(__file__).resolve().parent / ".env"
config = dotenv_values(str(env_path))

print("ENV FILE EXISTS:", env_path.exists())
print("ENV FILE PATH:", env_path)
print("ENV KEYS:", list(config.keys()))

supabase_url = config["SUPABASE_URL"]
supabase_key = config["SUPABASE_KEY"]
supabase_secret_key = config["SUPABASE_SECRET_KEY"]

print("SUPABASE URL LOADED:", bool(supabase_url))
print("SUPABASE KEY LOADED:", bool(supabase_key))
print("SUPABASE SECRET KEY LOADED:", bool(supabase_secret_key))


# --------------------------------------------------
# SUPABASE CLIENTS
# --------------------------------------------------

# Used for login and registration
auth_client = create_client(
    supabase_url,
    supabase_key
)

# Trusted server-side client
admin_client = create_client(
    supabase_url,
    supabase_secret_key
)


# --------------------------------------------------
# FLASK
# --------------------------------------------------

app = Flask(__name__)
app.secret_key = "student-notes-cloud-secret"


# --------------------------------------------------
# GET SUPABASE CLIENT
# --------------------------------------------------

def get_user_supabase():

    if "user_id" not in session:
        return None

    return admin_client


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:

        user_supabase = get_user_supabase()

        if user_supabase is None:
            return redirect(url_for("login"))

        response = (
            user_supabase
            .table("notes")
            .select("filename, created_at")
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )

        notes = response.data

        return render_template(
            "index.html",
            notes=notes
        )

    except Exception as e:

        print("HOME ERROR:", repr(e))

        flash(f"Home error: {e}")

        return render_template(
            "index.html",
            notes=[]
        )


# --------------------------------------------------
# UPLOAD
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():

    if "user_id" not in session:
        return redirect(url_for("login"))

    files = request.files.getlist("files")

    if not files or all(file.filename == "" for file in files):

        flash("Please choose at least one file.")

        return redirect(url_for("home"))

    user_supabase = get_user_supabase()

    if user_supabase is None:

        flash("Please log in again.")

        return redirect(url_for("login"))

    uploaded_count = 0

    for file in files:

        if not file or file.filename == "":
            continue

        filename = file.filename.strip()

        if filename == "":
            continue

        try:

            # Check if this user already has the filename
            existing = (
                user_supabase
                .table("notes")
                .select("id")
                .eq("user_id", session["user_id"])
                .eq("filename", filename)
                .execute()
            )

            if existing.data:

                flash(
                    f"{filename} already exists."
                )

                continue

            file_data = file.read()

            print("UPLOADING FILE:", filename)

            # Upload file to Supabase Storage
            user_supabase.storage.from_("notes").upload(
                filename,
                file_data,
                {
                    "upsert": "false"
                }
            )

            print(
                "STORAGE UPLOAD SUCCESS:",
                filename
            )

            # Save file information in database
            result = (
                user_supabase
                .table("notes")
                .insert({
                    "user_id": session["user_id"],
                    "filename": filename
                })
                .execute()
            )

            print(
                "DATABASE INSERT SUCCESS:",
                result.data
            )

            uploaded_count += 1

        except Exception as e:

            print(
                "UPLOAD ERROR:",
                repr(e)
            )

            # If database insertion failed after
            # Storage upload, remove the orphaned file.
            try:

                user_supabase.storage.from_("notes").remove(
                    [filename]
                )

            except Exception as cleanup_error:

                print(
                    "UPLOAD CLEANUP ERROR:",
                    repr(cleanup_error)
                )

            flash(
                f"Upload error for {filename}: {e}"
            )

    if uploaded_count > 0:

        flash(
            f"{uploaded_count} file(s) uploaded successfully."
        )

    return redirect(url_for("home"))


# --------------------------------------------------
# DOWNLOAD
# --------------------------------------------------

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:

        user_supabase = get_user_supabase()

        if user_supabase is None:
            return redirect(url_for("login"))

        # Check that this file belongs to the user
        result = (
            user_supabase
            .table("notes")
            .select("filename")
            .eq("user_id", session["user_id"])
            .eq("filename", filename)
            .execute()
        )

        if not result.data:

            flash(
                "You do not have permission to download this file."
            )

            return redirect(url_for("home"))

        # Download actual file from Storage
        file_data = (
            user_supabase
            .storage
            .from_("notes")
            .download(filename)
        )

        response = app.response_class(
            file_data,
            mimetype="application/octet-stream"
        )

        response.headers["Content-Disposition"] = (
            f'attachment; filename="{Path(filename).name}"'
        )

        return response

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

        flash(
            f"Download error: {e}"
        )

        return redirect(url_for("home"))


# --------------------------------------------------
# DELETE
# --------------------------------------------------

@app.route("/delete/<path:filename>", methods=["POST"])
def delete_file(filename):

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:

        user_supabase = get_user_supabase()

        if user_supabase is None:

            flash("Please log in again.")

            return redirect(url_for("login"))

        # ------------------------------------------
        # STEP 1: Check ownership
        # ------------------------------------------

        result = (
            user_supabase
            .table("notes")
            .select("filename")
            .eq("user_id", session["user_id"])
            .eq("filename", filename)
            .execute()
        )

        if not result.data:

            flash(
                "You do not have permission to delete this file."
            )

            return redirect(url_for("home"))

        # ------------------------------------------
        # STEP 2: Delete from Supabase Storage
        # ------------------------------------------

        print(
            "DELETING FROM STORAGE:",
            filename
        )

        user_supabase.storage.from_("notes").remove(
            [filename]
        )

        print(
            "STORAGE DELETE SUCCESS:",
            filename
        )

        # ------------------------------------------
        # STEP 3: Delete database record
        # ------------------------------------------

        print(
            "DELETING DATABASE RECORD:",
            filename
        )

        user_supabase \
            .table("notes") \
            .delete() \
            .eq("user_id", session["user_id"]) \
            .eq("filename", filename) \
            .execute()

        print(
            "DATABASE DELETE SUCCESS:",
            filename
        )

        flash(
            "File deleted successfully."
        )

    except Exception as e:

        print(
            "DELETE ERROR:",
            repr(e)
        )

        flash(
            f"Delete error: {e}"
        )

    return redirect(url_for("home"))


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        try:

            result = auth_client.auth.sign_up({
                "email": email,
                "password": password
            })

            print(
                "REGISTER USER:",
                result.user
            )

            flash(
                "Registration successful. You can now log in."
            )

            return redirect(
                url_for("login")
            )

        except Exception as e:

            print(
                "REGISTER ERROR:",
                repr(e)
            )

            flash(
                f"Registration error: {e}"
            )

    return render_template(
        "register.html"
    )


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        try:

            result = auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            print(
                "LOGIN USER:",
                result.user.id
            )

            if not result.session:

                flash(
                    "Login succeeded but Supabase did not return a session."
                )

                return redirect(
                    url_for("login")
                )

            # Store user identity in Flask session
            session["user_id"] = result.user.id
            session["email"] = result.user.email

            print(
                "USER ID SAVED:",
                session["user_id"]
            )

            flash(
                "Login successful."
            )

            return redirect(
                url_for("home")
            )

        except Exception as e:

            print(
                "LOGIN ERROR:",
                repr(e)
            )

            flash(
                f"Login error: {e}"
            )

    return render_template(
        "login.html"
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    try:

        auth_client.auth.sign_out()

    except Exception as e:

        print(
            "LOGOUT ERROR:",
            repr(e)
        )

    session.clear()

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("login")
    )


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=True
    )