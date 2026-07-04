Terminal 1 — Main backend (port 5000)
cd c:\London_Cycle_Maps\4_backend_engine
pip install -r requirements.txt
python app.py
Wait until you see the graph loaded message. First start can take a while.
Optional forced mode (dev): `python app.py --day` or `python app.py --night` — overrides the real sun position for the light_weight gating (night_time.is_dark). No flag = automatic.

Terminal 2 — Main frontend (port 3000)  
cd c:\London_Cycle_Maps\5_frontend  
npm start  
Optional forced mode (dev): `npm start -- --day` or `npm start -- --night` — skips the sunrise/sunset auto-detection and forces the initial Night Mode toggle/theme. No flag = automatic. (Handled by 5_frontend/start.js, which sets REACT_APP_FORCE_MODE.)  
Copy `5_frontend/.env.example` to `5_frontend/.env` and set `REACT_APP_MAPBOX_API_KEY` to your Mapbox public token (required for Start/End location search). Restart `npm start` after creating or editing `.env` — Create React App only reads env at startup.  
Opens [http://localhost:3000](http://localhost:3000) → talks to 5000 (hardcoded in 5_frontend/src/App.js).

Terminal 3 — Debug backend (port 5001)
cd c:\London_Cycle_Maps\4_backend_engine
python app_debug.py
Runs on 5001 so it doesn’t clash with main.

Terminal 4 — Debug frontend (port 3001)
Both CRA apps default to 3000, so set PORT for the debug UI:

cd c:\London_Cycle_Maps\8_debug\5_frontend
$env:PORT=3001; npm start  
  
Special case commands:   
**Automatic (normal behaviour, follows the real sun):**

*# Terminal 1 — backend*

cd c:\London_Cycle_Maps\4_backend_engine

python [app.py](http://app.py)

*# Terminal 2 — frontend*

cd c:\London_Cycle_Maps\5_frontend

npm start

**Forced day mode (work on day mode at night):**

*# Terminal 1 — backend*

cd c:\London_Cycle_Maps\4_backend_engine

python [app.py](http://app.py) --day

*# Terminal 2 — frontend*

cd c:\London_Cycle_Maps\5_frontend

npm start -- --day

**Forced night mode (work on night mode during the day):**

*# Terminal 1 — backend*

cd c:\London_Cycle_Maps\4_backend_engine

python [app.py](http://app.py) --night

*# Terminal 2 — frontend*

cd c:\London_Cycle_Maps\5_frontend

npm start -- --night