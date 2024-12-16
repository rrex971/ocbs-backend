from fastapi import FastAPI
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
    db = sqlite3.connect("data.db", check_same_thread=False, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    c = db.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (apiId TEXT, clientObject JSON)")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=6969)
