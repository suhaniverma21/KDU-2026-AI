# FastAPI Multimodal AI Assistant

## Overview
This project is a FastAPI-based multimodal AI assistant backend.

In simple words, it is a backend system that lets a user:
- create an account
- log in securely
- save a personal profile
- chat with an AI assistant
- ask for weather information
- analyze images
- get responses that remember context

It solves the problem of building a basic AI assistant that is not just a plain chatbot. Instead of answering every message in isolation, this assistant can use user profile data, recent conversation history, past conversations, and simple tools.

### What “multimodal AI assistant” means
“Multimodal” means the assistant can understand more than one kind of input.

In this project, that means:
- text input
- image input

So the assistant can respond to normal messages and also analyze images.

### What “context-aware” means
“Context-aware” means the assistant does not only look at the current message.

It can also use:
- the user’s saved profile
- recent messages from the current session
- messages from older sessions
- a summary of long conversations

That helps the assistant give more relevant responses.

## Key Features
- User authentication with JWT
- User profile storage with location and style
- General chat using LangChain and OpenAI
- Weather tool that can use the saved profile location
- Image analysis for multimodal requests
- Router for task selection
- Style-based personalization
- Short-term memory for current session context
- Cross-session memory using simple database search
- Conversation summarization for long sessions
- Model switching for cost-aware task handling
- Guardrails for input, processing, and output safety
- Structured JSON responses across the API

## Architecture Overview
At a high level, the system works like this:

1. The client sends a request to the FastAPI server.
2. The server checks authentication if the endpoint is protected.
3. The server loads user data from MySQL.
4. The router decides what kind of task the request is.
5. The correct flow runs:
   - chat
   - weather
   - image analysis
6. The result is validated and returned as structured JSON.

### Simple architecture flow
```text
Client
  ->
FastAPI API
  ->
Authentication
  ->
MySQL Database
  ->
Router
  -> Chat Flow
  -> Weather Tool
  -> Image Analysis
  ->
Structured JSON Response
```

## Project Structure
```text
project/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── auth.py
│   ├── chat_service.py
│   ├── middleware/
│   │   └── style_middleware.py
│   ├── agents/
│   │   ├── router.py
│   │   ├── image.py
│   │   └── model_selector.py
│   ├── tools/
│   │   └── weather_tool.py
│   └── utils/
│       └── safety.py
├── sql/
│   └── schema.sql
├── requirements.txt
├── .env
└── README.md
```

### Folder and file explanation

#### `app/main.py`
- Main FastAPI application entry point
- Defines the API endpoints
- Connects auth, database, router, tools, memory, and response models

#### `app/config.py`
- Loads environment variables from `.env`
- Stores settings like:
  - `DATABASE_URL`
  - `GOOGLE_API_KEY`
  - `OPENWEATHER_API_KEY`
  - `JWT_SECRET_KEY`
  - model names

#### `app/database.py`
- Contains MySQL helper functions
- Handles:
  - DB connection
  - user queries
  - profile updates
  - conversation storage
  - session history
  - summaries

#### `app/models.py`
- Contains Pydantic models
- Used for:
  - validating request data
  - standardizing response JSON

#### `app/auth.py`
- Handles JWT authentication
- Hashes passwords
- Verifies passwords
- Creates tokens
- Loads the current user from the token

#### `app/middleware/style_middleware.py`
- Contains style and tone helpers
- Applies user response style like:
  - `expert`
  - `child`
  - `casual`
- Supports simple temporary tone overrides from the current message

#### `app/agents/router.py`
- Decides what type of request is being handled
- Selects:
  - `chat`
  - `weather`
  - `image`
  - `memory_chat`

#### `app/agents/image.py`
- Handles image analysis requests
- Sends text + image to a vision-capable OpenAI model
- Returns structured image analysis JSON

#### `app/agents/model_selector.py`
- Chooses which model to use for each task
- Uses a smaller model for normal chat and summaries
- Uses a stronger vision model for image analysis

#### `app/tools/weather_tool.py`
- Calls the OpenWeatherMap API
- Returns structured weather information

#### `app/utils/safety.py`
- Contains guardrails and validation helpers
- Checks input safety, processing safety, and output safety

#### `sql/schema.sql`
- Creates the MySQL tables used in the project:
  - `users`
  - `conversations`
  - `conversation_summaries`

#### `requirements.txt`
- Lists all Python dependencies

#### `.env`
- Stores local configuration and secret keys

## Tech Stack
- FastAPI
- MySQL
- LangChain
- OpenAI (`gpt-4o`, `gpt-4o-mini`)
- Pydantic
- JWT Authentication
- HTTPX
- Passlib
- Python JOSE

## Setup Instructions

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd AI-Assistant
```

### 2. Create a virtual environment
```bash
python -m venv venv
```

### 3. Activate the virtual environment

On Windows:
```bash
venv\Scripts\activate
```

On Linux/Mac:
```bash
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Create the MySQL database
Open MySQL and run:

```sql
CREATE DATABASE IF NOT EXISTS assistant_db;
USE assistant_db;
SOURCE sql/schema.sql;
```

If `SOURCE` does not work, copy and run the SQL manually from [`sql/schema.sql`](./sql/schema.sql).

### 6. Update the `.env` file
Fill in your database connection and API keys.

### 7. Run the server
```bash
uvicorn app.main:app --reload
```

The API will be available at:
```text
http://127.0.0.1:8000
```

## `.env` Example
```env
DATABASE_URL=mysql+mysqlconnector://assistant_user:assistant123@localhost:3306/assistant_db
GOOGLE_API_KEY=your-google-api-key
OPENWEATHER_API_KEY=your-openweather-api-key
JWT_SECRET_KEY=your-jwt-secret-key
TEXT_MODEL=gemini-2.5-flash-lite
VISION_MODEL=gemini-2.5-flash
```

### What each variable means
- `DATABASE_URL`: MySQL connection string
- `GOOGLE_API_KEY`: key used for chat, summaries, routing fallback, and image analysis
- `OPENWEATHER_API_KEY`: key used for live weather lookup
- `JWT_SECRET_KEY`: secret used to sign JWT tokens
- `TEXT_MODEL`: model used for normal chat and summarization
- `VISION_MODEL`: model used for image analysis

## API Endpoints

### `POST /signup`
Creates a new user account.

#### Example request
```json
{
  "email": "demo@example.com",
  "password": "mypassword123"
}
```

#### Example response
```json
{
  "message": "User created successfully"
}
```

---

### `POST /login`
Logs in the user and returns a JWT token.

#### Example request
```json
{
  "email": "demo@example.com",
  "password": "mypassword123"
}
```

#### Example response
```json
{
  "access_token": "your-jwt-token",
  "token_type": "bearer"
}
```

---

### `GET /profile`
Returns the current authenticated user’s profile.

#### Example response
```json
{
  "email": "demo@example.com",
  "location": "Bengaluru",
  "style": "casual"
}
```

---

### `PUT /profile`
Updates the current user’s profile.

#### Example request
```json
{
  "location": "Bengaluru",
  "style": "expert"
}
```

#### Example response
```json
{
  "email": "demo@example.com",
  "location": "Bengaluru",
  "style": "expert"
}
```

---

### `POST /chat`
Handles chat, weather, memory-aware chat, and image analysis depending on the request.

#### Example normal chat request
```json
{
  "message": "Explain Python loops",
  "session_id": "session-1"
}
```

#### Example normal chat response
```json
{
  "session_id": "session-1",
  "reply": "Python loops let you repeat actions without writing the same code again.",
  "style": "casual",
  "route": "chat",
  "model_used": "gpt-4o-mini"
}
```

#### Example weather response
```json
{
  "temperature": 29.4,
  "summary": "Clear Sky",
  "location": "Bengaluru",
  "route": "weather",
  "model_used": null
}
```

#### Example image response
```json
{
  "description": "A dog sitting on green grass",
  "objects": ["dog", "grass"],
  "scene_type": "outdoor",
  "safety_rating": "safe",
  "route": "image",
  "model_used": "gpt-4o"
}
```

---

### `GET /history`
Returns recent messages for a session.

#### Example request
```text
GET /history?session_id=session-1
```

#### Example response
```json
{
  "session_id": "session-1",
  "messages": [
    {
      "role": "user",
      "content": "Explain Python loops",
      "created_at": "2026-04-11T10:15:00"
    },
    {
      "role": "assistant",
      "content": "Python loops let you repeat actions without writing the same code again.",
      "created_at": "2026-04-11T10:15:02"
    }
  ]
}
```

## Example Use Cases

### Example 1: Weather using saved location
User:
```text
What’s the weather?
```

Flow:
- user is authenticated
- profile is loaded
- saved `location` is used
- weather tool calls OpenWeatherMap
- structured weather JSON is returned

### Example 2: Image analysis
User:
```text
Describe this image
```

With:
```json
{
  "image_url": "https://example.com/cat.jpg"
}
```

Flow:
- router selects `image`
- image analysis model runs
- structured image result is returned

### Example 3: Cross-session memory
User:
```text
What did I say earlier about loops?
```

Flow:
- router may choose `memory_chat`
- app searches older conversations for the same user
- past messages are added to prompt context
- assistant responds with better continuity

### Example 4: Style-based response
User profile style:
```text
child
```

User asks:
```text
Explain gravity
```

Flow:
- app loads the saved style
- system prompt becomes simpler
- response is easier to understand

## Memory System

### 1. Short-term memory
This uses recent messages from the current session.

Example:
- User: “Explain variables”
- Assistant: “Variables store values”
- User: “Give an example”

The assistant can understand what “an example” refers to because it sees recent session history.

### 2. Cross-session memory
This searches older conversations for the same user using simple keyword search.

Example:
- Earlier session: “Help me learn loops”
- New session: “What did we discuss about loops?”

The app searches older messages and adds matching ones as extra context.

### 3. Summarization
If a session gets long, older messages are summarized into short bullet points.

This helps reduce prompt size while keeping:
- user goals
- important topics
- preferences

The newest messages are still kept in full detail.

## Model Switching
This project uses simple model switching:

- `TEXT_MODEL` for:
  - general chat
  - session summarization
  - routing fallback classification

- `VISION_MODEL` for:
  - image analysis

### Why this helps
- normal chat does not always need the strongest model
- image tasks need a vision-capable model
- using a smaller model for text can reduce cost

## Guardrails
This project includes a basic safety layer.

### Input checks
- empty input
- overly long input
- repeated-character spam
- suspicious jailbreak phrases
- invalid image URLs

### Processing checks
- only approved routes are allowed
- weather location is validated
- image input is validated
- memory queries stay scoped to the authenticated user

### Output checks
- text output is checked for unsafe patterns
- prompt leakage is checked
- structured outputs are validated with Pydantic

### Why safety matters
Safety checks help avoid:
- malformed requests
- prompt injection attempts
- broken tool calls
- inconsistent output

This is still a beginner-friendly safety layer, not a production-grade moderation system.

## Limitations
- Routing is improved but still partly rule-based
- Safety checks are basic and not production-grade
- Cross-session memory uses simple keyword search, not vector search
- Summarization is simple and stored as one rolling summary
- Weather flow depends on a valid OpenWeatherMap API key
- Image analysis depends on a valid OpenAI API key and accessible image input

## Future Improvements
- better LLM-based routing
- stronger safety using moderation APIs
- vector-based memory search
- more advanced summarization
- improved image analysis pipeline
- richer frontend integration

## Demo Instructions
You can test the project using Swagger UI:

```text
http://127.0.0.1:8000/docs
```

### Recommended testing order
1. `GET /health`
2. `GET /db-check`
3. `POST /signup`
4. `POST /login`
5. Click `Authorize` and paste:

```text
Bearer your-jwt-token
```

6. Test:
- `GET /profile`
- `PUT /profile`
- `POST /chat`
- `GET /history`

## Conclusion
This project demonstrates how to build a structured, context-aware, multimodal AI assistant backend using FastAPI, MySQL, LangChain, and OpenAI.

It shows practical backend engineering skills such as:
- authentication
- profile management
- tool integration
- multimodal support
- memory systems
- prompt design
- model selection
- response validation
- safety guardrails

It is also a strong learning project because each feature was added step by step, making the architecture easier to understand and explain.
