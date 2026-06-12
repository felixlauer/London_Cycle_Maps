Terminal 1 — Main backend (port 5000)
cd c:\London_Cycle_Maps\4_backend_engine
python app.py
Wait until you see the graph loaded message. First start can take a while.

Terminal 2 — Main frontend (port 3000)
cd c:\London_Cycle_Maps\5_frontend
npm start
Opens http://localhost:3000 → talks to 5000 (hardcoded in 5_frontend/src/App.js).

Terminal 3 — Debug backend (port 5001)
cd c:\London_Cycle_Maps\4_backend_engine
python app_debug.py
Runs on 5001 so it doesn’t clash with main.

Terminal 4 — Debug frontend (port 3001)
Both CRA apps default to 3000, so set PORT for the debug UI:


cd c:\London_Cycle_Maps\8_debug\5_frontend
$env:PORT=3001; npm start