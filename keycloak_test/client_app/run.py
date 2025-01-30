import os
from flask import Flask, redirect, url_for, session, render_template_string
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET"),
    server_metadata_url=os.getenv("KEYCLOAK_SERVER_METADATA_URL"),
    client_kwargs={"scope": "openid profile email"},
)

@app.route("/")
def index():
    user = session.get("user")
    if user:
        import json
        print(json.dumps(user, indent=4))
        return render_template_string('''
            <h1>Welcome, {{ user['name'] }}!</h1>
            <form action="{{ url_for('logout') }}" method="post">
                <button type="submit">Logout</button>
            </form>
        ''', user=user)
    else:        
        return render_template_string('''
            <h1>Hello, you are not logged in.</h1>
            <form action="{{ url_for('login') }}" method="post">
                <button type="submit">Login</button>
            </form>
        ''')

# Login page
@app.route("/login", methods=["POST"])
def login():
    redirect_uri = url_for("auth", _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)

# Auth callback
@app.route("/auth")
def auth():
    token = oauth.keycloak.authorize_access_token()
    # import json
    # print(json.dumps(token, indent=4))
    session["user"] = oauth.keycloak.parse_id_token(token, nonce=token.get("nonce"))
    # session['token'] = token
    return redirect("/")

# Logout
@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    # session.pop("token", None)
    logout_url = f"{os.getenv('KEYCLOAK_LOGOUT_URL')}?post_logout_redirect_uri={url_for('index', _external=True)}&client_id={os.getenv('KEYCLOAK_CLIENT_ID')}"
    return redirect(logout_url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)