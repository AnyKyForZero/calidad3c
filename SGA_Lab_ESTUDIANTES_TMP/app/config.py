from pathlib import Path
class Config:
    SECRET_KEY='sga-lab-secret'
    DATABASE=Path(__file__).resolve().parent.parent/'instance'/'sga.db'
