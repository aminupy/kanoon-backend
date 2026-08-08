# Blog publishing

## Lifecycle and permissions

Blog uses the existing `blog` tenant capability. Disabled tenants receive the same generic 404
feature response from public and administration routes. `content:read` reads drafts,
`content:write` creates/autosaves drafts, and `content:publish` publishes, changes already-public
posts, and archives them. `CONTENT_EDITOR` intentionally cannot publish; `TENANT_ADMIN` can.

`POST /api/v1/admin/blog` always creates `DRAFT`. Draft PATCH requests and media uploads never
change the site revision or create builds. Publication is explicit through
`POST /api/v1/admin/blog/{id}/publish`. PATCH of a `PUBLISHED` post is an explicit public save: it
updates canonical CMS state and requests a coalesced build. Admin UIs must only autosave drafts and
must present an explicit save-public action for published posts. Archiving a published post requests
a build; archiving a draft does not.

The legacy generic `/admin/posts` write endpoints reject BLOG input so callers cannot bypass these
semantics. NEWS and ANNOUNCEMENT remain on the generic contract.

## Structured rich text and media

`posts.content_document` is canonical TipTap/ProseMirror-compatible JSONB. The allowlist supports
documents, headings, paragraphs, text, bold/italic/underline/link marks, ordered/unordered lists,
list items, blockquotes, horizontal rules, hard breaks, and media images with optional alt/caption.
Unknown nodes, fields, marks, unsafe URLs, excessive depth/size, and arbitrary HTML are rejected.

FastAPI deterministically produces `rendered_html`. Text and attributes are escaped; only known HTML
elements are emitted; HTTP(S) links receive `target=_blank` and `rel="noopener noreferrer"`.
Administrators never submit canonical HTML.

Image nodes store only a stable UUID:

```json
{"type":"image","attrs":{"media_id":"<uuid>","alt":"...","caption":"..."}}
```

`post_media_references` records inline references with tenant-composite foreign keys. Cover and OG
images also use composite `(tenant_id, media_id)` foreign keys. Draft saves require an existing
same-tenant asset; publication additionally requires every asset to be READY and PUBLIC. Public HTML
uses `/api/v1/public/media/{uuid}`, a stable application URL that obtains a fresh inline object-store
redirect at request time. Presigned URLs are never persisted or emitted into the static projection.
Uploads are not deleted when a draft is removed. A future orphan collector must check all reference
tables and use an age grace period before deleting object metadata/storage.

## Public contracts

- `GET /api/v1/public/blog` returns published summaries, ordered by `published_at DESC, id DESC`.
- `GET /api/v1/public/blog/{slug}` returns one published structured/rendered post.
- `GET /api/v1/public/blog/snapshot?requested_revision=N` returns all published blog data plus the
  current revision and echoes the requested revision.

Public schemas omit database audit identities and build/storage configuration. SEO title,
description, and OG image are optional; title, summary, and cover image are their fallbacks.
