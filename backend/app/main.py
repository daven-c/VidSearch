from fastapi import FastAPI, File, UploadFile, Query

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Hello World"}


@app.get("/asfsda")
def asfsda():
    return {"message": "Hello World"}
