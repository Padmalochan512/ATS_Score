import logging
from contextlib import asynccontextmanager
import hashlib

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from backend.api.routes import router

from backend.core.config import(
    ALLOWED_ORIGINS, 
    APP_DESCRIPTION, 
    APP_TITLE, 
    APP_VERSION, 
    SPACY_MODEL_PRIMARY, 
    SPACY_MODEL_SECONDARY, SENTENCE_TRANSFORMER_MODEL
)
from backend.api.routes import router

logger=logging.getLogger('ats_resume_scorer')


class _FallbackSentenceTransformer:
    """Offline-safe embedding fallback using deterministic hashed bag-of-words vectors."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def encode(self, text, convert_to_tensor=False):
        if isinstance(text, (list, tuple)):
            vectors = [self._encode_one(item) for item in text]
            return np.vstack(vectors)
        return self._encode_one(text)

    def _encode_one(self, text):
        vector = np.zeros(self.dimensions, dtype=np.float32)
        tokens = str(text or "").lower().split()
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector


@asynccontextmanager
async def lifespan(app:FastAPI):
    app.state.nlp = None
    app.state.embedder = None

    logger.info(f'Loading spaCy NLP model: {SPACY_MODEL_PRIMARY}')
    import spacy
    try:
        app.state.nlp = spacy.load(SPACY_MODEL_PRIMARY)
        logger.info(f'Loaded {SPACY_MODEL_PRIMARY}')
    except Exception:
        logger.warning(f'{SPACY_MODEL_PRIMARY} not found — falling back to {SPACY_MODEL_SECONDARY}')
        try:
            app.state.nlp = spacy.load(SPACY_MODEL_SECONDARY)
            logger.info(f'Loaded {SPACY_MODEL_SECONDARY} (fallback)')
        except Exception:
            logger.warning('spaCy models unavailable; using blank English pipeline.')
            app.state.nlp = spacy.blank('en')

    logger.info(f'Loading SentenceTransformer: {SENTENCE_TRANSFORMER_MODEL}')
    try:
        from sentence_transformers import SentenceTransformer

        app.state.embedder = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        logger.info(f'Loaded {SENTENCE_TRANSFORMER_MODEL}')
    except Exception as exc:
        logger.warning(f'SentenceTransformer unavailable; using offline fallback: {exc}')
        app.state.embedder = _FallbackSentenceTransformer()

    logger.info('All models loaded. API is ready to serve requests.')

    yield

    logger.info('shutting down the api!!')

app=FastAPI(
    title=APP_TITLE, 
    description=APP_DESCRIPTION, 
    version=APP_VERSION, 
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc'
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True, 
    allow_methods     = ['*'],
    allow_headers     = ['*'],

)

app.include_router(router)

@app.get('/')
async def root():
    return {
        'name':      'ATS Resume Analyzer API',
        'version':   '2.0.0',
        'endpoints': {
            'POST   /api/v1/analyze-resume': 'Analyze a resume',
            'GET    /api/v1/history':        'Get user history',
            'DELETE /api/v1/history/:id':    'Delete a history entry',
            'POST   /api/v1/auth/login-event': 'Record a successful login event',
            'GET    /api/v1/admin/dashboard':  'Owner-only dashboard data',
            'GET    /api/v1/health':         'Health check',
            'POST   /api/v1/generate-pdf':   'Generate PDF report from data',
        },
    }

if __name__=='__main__':
    import uvicorn
    uvicorn.run(
        'backend.main:app',
        host    = '0.0.0.0',
        port    = 8000,
        reload  = True,    # Auto-restart on code changes (dev only)
    )
