Streamlit Poster Generator

This folder contains a small Streamlit app that uses the project's poster generation logic.

Files:
- `app.py` - the Streamlit app UI + generation logic
- `background.png`, `logo.png` - default images (already copied here). The app loads these automatically.
- `requirements.txt` - dependencies to install (streamlit, Pillow)

How to run:
1. Create and activate a virtual environment.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

2. Run the app from the `streamlit_app` folder:

```powershell
cd streamlit_app; streamlit run app.py
```

Notes:
- The UI lets you enter the text for positions 1 (title), 2 (subtitle), and 3 (body). It will use the exact coordinates from the repository `positions.json` when available.
- `background.png` and `logo.png` are loaded automatically from this folder (no upload needed).
- You can upload additional images via the sidebar — these will be placed in the center of the poster (like the assets folder in the original `poster_generator.py`).
- Generated posters can be downloaded as JPEG or saved to `streamlit_app/output/`.
