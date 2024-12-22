from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware

from osu import Client, AuthHandler, Scope
from dotenv import load_dotenv
import os
import sqlite3
import json


load_dotenv()
client_id = int(os.getenv('osu_client_id'))
client_secret = os.getenv('osu_client_secret')
redirect_url = os.getenv('redirect_uri')

def load_db():
    global c, db
    db = sqlite3.connect("data.db", isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    c = db.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (apiId TEXT, clientObject JSON)")
    c.execute("CREATE TABLE IF NOT EXISTS registrations (username TEXT, userId TEXT, avatarurl TEXT, rank INTEGER, discordUsername TEXT, paymentReceived BOOLEAN DEFAULT FALSE)")
    return c, db



c, db = load_db()

app = FastAPI()

origins = [
    "http://localhost:5173", # for local development
    "https://ocbs.rrex.cc"  
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range"],
    max_age=3600,
)

@app.get("/api/")
async def root():
    return {"message": "Backend API for the OCBS website. Not for public use."}


@app.get("/api/loginFlow")
async def loginFlow(apiId: str, code: str):
    
    auth = AuthHandler(client_id, client_secret, redirect_url, Scope.identify())
    print(code)
    if code != None and code != "":
        auth.get_auth_token(code)
        
        client = Client(auth)
        c.execute("INSERT INTO users (apiId, clientObject) VALUES (?, ?)", (apiId, json.dumps(auth.get_save_data())))
        userdata = client.get_own_data()
        return {
            "username": userdata.username,
            "userId": userdata.id,
            "avatar": userdata.avatar_url
        }
    else:
        return {"error": "No code provided"}

@app.post("/api/registration")
async def registration(request: Request):
    data = await request.json()
    api_id = data.get("api_id")
    username = data.get("username")
    user_id = data.get("id")
    discord_username = data.get("discord_username")
    phone_number = data.get("phone_number")

    if not all([api_id, username, user_id, discord_username, phone_number]):
        return JSONResponse(status_code=400, content={"error": "Missing registration data"})
    userAuth = AuthHandler.from_save_data(json.loads(c.execute("SELECT clientObject FROM users WHERE apiId = ?", (api_id,)).fetchone()[0]))
    client = Client(userAuth)
    data = client.get_own_data()
    avatar_url = data.avatar_url
    rank = data.statistics.global_rank
    c.execute("DELETE FROM users WHERE apiId = ?", (api_id,))
    c.execute("INSERT INTO users (apiId, clientObject) VALUES (?, ?)", (api_id, json.dumps(userAuth.get_save_data()))) # refresh the auth token

    c.execute("INSERT INTO registrations (username, userId, avatarurl, rank, discordUsername) VALUES (?, ?, ?, ?, ?)", (username, user_id, avatar_url, rank, discord_username))
    file = open("registration.txt", "a");
    file.write(f"{username}, {phone_number}\n")
    file.close()
    return JSONResponse(status_code=200, content={"message": "Registration successful"})

@app.get("/api/registrations")
async def registrations():
    c.execute("SELECT * FROM registrations WHERE paymentReceived = 1")
    rows = c.fetchall()
    column_names = [description[0] for description in c.description]
    response = [dict(zip(column_names, row)) for row in rows]
    return JSONResponse(content=response)

@app.get("/api/userExists")
async def userExists(userId: str):
    c.execute("SELECT * FROM registrations WHERE userId = ?", (userId,))
    return c.fetchone() != None

@app.get("/api/paymentStatus")
async def paymentStatus(userId: str):
    c.execute("SELECT paymentReceived FROM registrations WHERE userId = ?", (userId,))
    return c.fetchone()[0]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=6969)
