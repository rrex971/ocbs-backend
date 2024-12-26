from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware
import csv
from osu import Client, AuthHandler, Scope, Mods
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

def OverallDifficultyToMs(OD):
    return -6 * OD + 79.5
def MsToOverallDifficulty(ms):
    return (79.5 - ms) / 6
def CalculateMultipliedOD(OD, multiplier):
    newbpmMS = OverallDifficultyToMs(OD) / multiplier
    newbpmOD = MsToOverallDifficulty(newbpmMS)
    newbpmOD = round(newbpmOD*10)/10
    return newbpmOD

def getMapAttr(cs, hp, ar, od, bpm, mod):
    if mod == Mods.HardRock:
        cs *= 1.3
        if cs>10:cs=10
        hp *= 1.4
        if hp>10:hp=10
        ar *= 1.4
        if ar>10:ar=10
        od *= 1.4
        if od>10:od=10
    if mod == Mods.DoubleTime:
        bpm *= 1.5
        ar=round(((ar*2)+13)/3, 2)
        od = CalculateMultipliedOD(od, 1.5)
    return {
        "ar" : round(ar, 2),
        "od": round(od, 2),
        "cs": round(cs, 2),
        "hp": round(hp, 2),
        "bpm": round(bpm, 2)
    }

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
    c.execute("SELECT * FROM registrations WHERE paymentReceived = 1 ORDER BY rank")
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
    
    res = c.fetchone()
    if res == None:
        return JSONResponse(status_code=404, content={"error": "User doesn't exist"})
    else:   
        return res[0]

@app.get("/api/getMappools")
async def getMappools(stage: int): # 0 = qualifiers, 1 = grand finals, 2 = testing
    filename = ["qualifiers.json", "grandfinals.json", "testing.json"][stage]
    try:
        with open(filename, "r") as f:
            return JSONResponse(content=json.load(f))
    except FileNotFoundError:
        return JSONResponse(content=load_map_pools(stage), status_code=201)

def load_map_pools(stage: int):
    
    auth = AuthHandler(client_id, client_secret, redirect_url, Scope.identify())
    auth.get_auth_token()
    client = Client(auth)

    mp = {
        "NM": [],
        "HD": [],
        "HR": [],
        "DT": [],
        "TB": [],
    }
    filename = ["qualifiers.csv", "grandfinals.csv", "testing.csv"][stage]
    with open(filename, "r") as f:
        csvreader = csv.reader(f)
        next(csvreader)
        for row in csvreader:
            mp[row[0]].append({
                "pick": row[0]+str(row[1]),
                "mapId": row[2],
            })
        
        for pick in mp.keys():
            for pickMap in mp[pick]:
                mapInfo = client.get_beatmap(int(pickMap["mapId"]))
                mod = Mods.get_from_abbreviation(pick) if pick not in ["TB", "NM"] else None
                mapInfoAttr = client.get_beatmap_attributes(int(pickMap["mapId"]), mods=mod)
                diffAttr = getMapAttr(cs=mapInfo.cs, hp=mapInfo.drain, ar=mapInfo.ar, od=mapInfo.accuracy, bpm=mapInfo.bpm, mod=mod)
                pickMap["bg"]=mapInfo.beatmapset.background_url
                pickMap["artist"] = mapInfo.beatmapset.artist
                pickMap["title"] = mapInfo.beatmapset.title
                pickMap["diff"] = mapInfo.version
                pickMap["creator"] = mapInfo.beatmapset.creator
                lgt = mapInfo.total_length if pick != "DT" else mapInfo.total_length//1.5
                minutes, seconds = divmod(mapInfo.total_length, 60)
                pickMap["length"] = f"{minutes}:{seconds:02d}"
                pickMap["link"] = f"https://osu.ppy.sh/b/{mapInfo.id}"
                pickMap["ar"]=diffAttr["ar"]
                pickMap["cs"]=diffAttr["cs"]
                pickMap["hp"]=diffAttr["hp"]
                pickMap["od"]=diffAttr["od"]
                pickMap["sr"]=round(mapInfoAttr.star_rating, 2)
                pickMap["bpm"]=diffAttr["bpm"]
    filename = ["qualifiers.json", "grandfinals.json", "testing.json"][stage]
    with open(filename, "w") as f:
        json.dump(mp, f)
    return mp


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=6969)
