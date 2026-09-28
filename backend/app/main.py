from fastapi import FastAPI

app = FastAPI(title="Email Agent API", version="1.0.0")


@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Email Agent API is running"}
