# BharatFinanceAI

Full-stack finance AI application with FastAPI backend.

## Project Structure

```
bharat-finance-ai/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── app/
│       ├── routes/
│       ├── services/
│       ├── utils/
│       └── models/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
└── README.md
```

## Setup

### Prerequisites

- Python 3.9 or higher
- pip

### Install Dependencies

1. Navigate to the backend directory:

   ```bash
   cd backend
   ```

2. Create a virtual environment (recommended):

   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:

   - **Windows:**
     ```bash
     venv\Scripts\activate
     ```
   - **macOS/Linux:**
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

### Run the Server

Start the FastAPI server using uvicorn:

```bash
uvicorn main:app --reload
```

- The API will be available at `http://127.0.0.1:8000`
- Interactive API docs (Swagger UI) at `http://127.0.0.1:8000/docs`
- Alternative API docs (ReDoc) at `http://127.0.0.1:8000/redoc`

The `--reload` flag enables auto-reload during development. For production, omit it:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Frontend

### Run the Frontend

1. Navigate to the frontend directory:

   ```bash
   cd frontend
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Start the development server:

   ```bash
   npm run dev
   ```

- The app will be available at `http://localhost:5173`
- Ensure the backend is running at `http://localhost:8000` for API calls

## API

| Endpoint | Method | Description        |
|----------|--------|--------------------|
| `/`      | GET    | Backend status     |
