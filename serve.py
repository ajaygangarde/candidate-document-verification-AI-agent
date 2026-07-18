import uvicorn

uvicorn.run("recruitment.app:app", reload=False, port=8080)
