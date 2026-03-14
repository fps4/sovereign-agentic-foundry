-- Creates a separate database for Woodpecker CI so it does not share
-- the platform application database. Runs once on first container start.
CREATE DATABASE woodpecker;
