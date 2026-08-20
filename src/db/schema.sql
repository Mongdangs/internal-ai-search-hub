PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    project_name TEXT,
    client_name TEXT,
    year TEXT,
    business_type TEXT,
    domain TEXT,
    folder_path TEXT,
    security_level TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    project_id TEXT,
    document_title TEXT,
    document_type TEXT,
    file_path TEXT,
    file_type TEXT,
    file_name TEXT,
    version TEXT,
    is_final INTEGER,
    indexed_at TEXT,
    access_acl TEXT,
    canonical_key TEXT,
    content_signature TEXT,
    file_mtime REAL,
    FOREIGN KEY(project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT,
    project_id TEXT,
    source_file TEXT,
    file_type TEXT,
    page_no INTEGER,
    display_page TEXT,
    page_range TEXT,
    chunk_index INTEGER,
    index_version TEXT,
    chapter_title TEXT,
    canonical_chapter_title TEXT,
    normalized_chapter_title TEXT,
    section_title TEXT,
    normalized_section_title TEXT,
    heading_path TEXT,
    normalized_heading_path TEXT,
    heading_norm TEXT,
    chunk_text TEXT,
    keywords TEXT,
    embedding_id TEXT,
    token_count INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    raw_chapter_title TEXT,
    raw_section_title TEXT,
    raw_heading_path TEXT,
    canonical_section_title TEXT,
    canonical_subsection_title TEXT,
    canonical_heading_path TEXT,
    heading_classification_confidence REAL,
    heading_classification_reason TEXT,
    table_type TEXT,
    table_title TEXT,
    table_headers TEXT,
    table_row_text TEXT,
    domain_keywords TEXT,
    parent_chunk_id TEXT,
    parent_context TEXT,
    embedding_text TEXT,
    created_at TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(document_id),
    FOREIGN KEY(project_id) REFERENCES projects(project_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    chunk_text,
    keywords,
    project_name,
    document_title
);

CREATE TABLE IF NOT EXISTS search_logs (
    log_id TEXT PRIMARY KEY,
    query_text TEXT,
    query_type TEXT,
    result_count INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS saved_searches (
    saved_search_id TEXT PRIMARY KEY,
    query_text TEXT,
    parsed_query_json TEXT,
    result_count INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS saved_evidence (
    evidence_id TEXT PRIMARY KEY,
    saved_search_id TEXT,
    chunk_id TEXT,
    document_id TEXT,
    page_no INTEGER,
    note TEXT,
    created_at TEXT,
    FOREIGN KEY(saved_search_id) REFERENCES saved_searches(saved_search_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_file_path ON documents(file_path);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_saved_evidence_search ON saved_evidence(saved_search_id);
