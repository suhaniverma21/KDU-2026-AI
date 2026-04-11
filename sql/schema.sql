-- Simple MySQL schema for user profiles.
-- This table stores one user's email plus their saved location and style.
-- It also stores a hashed password for login.
-- Run this file in MySQL before testing the profile endpoints.

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    location VARCHAR(255) DEFAULT '',
    style VARCHAR(50) DEFAULT 'casual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- This table stores each chat message for a specific user and session.
-- session_id lets us group messages that belong to the same conversation.
-- We save both user and assistant messages so we can show chat history later.
CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    image_url TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- This table stores one rolling summary for a session.
-- It helps us keep long chats shorter in the prompt while still
-- keeping the full original messages in the conversations table.
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_session_summary (user_id, session_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
