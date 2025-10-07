# Conditional HTTP Requests

Use If-Modified-Since and ETag headers.

## Why

Reduce bandwidth, respect API limits.

## Files to Check

- All `api/*.py` files

## Changes Needed

- Store Last-Modified and ETag from responses
- Send in subsequent requests
- Handle 304 Not Modified responses
