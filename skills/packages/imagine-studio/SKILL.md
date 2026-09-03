# Imagine Studio

Letterboxed device stills from the host screen. Not a text-to-image generator.

```http
GET /imagine
GET /v1/imagine
POST /v1/imagine/compose
{"mode":"rotato_phone","source":"live"}
POST /v1/skills/run
{"skill":"imagine_compose","params":{"mode":"macbook_web","source":"last"}}
```

Modes: `rotato_phone` · `macbook_web` · `clean`  
Sources: `live` · `last` · `novae` · `image_b64`
