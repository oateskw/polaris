# Meta App Review Demos

This folder contains standalone screencast scripts used for Meta app permission review.

Run from project root so local imports and database paths resolve correctly:

- `python demos/meta_review/demo_basic_permission.py`
- `python demos/meta_review/demo_business_management.py`
- `python demos/meta_review/demo_content_publish.py`
- `python demos/meta_review/demo_instagram_basic.py`
- `python demos/meta_review/demo_instagram_manage_messages.py`
- `python demos/meta_review/demo_manage_comments.py`
- `python demos/meta_review/demo_manage_insights.py`
- `python demos/meta_review/demo_manage_messages.py`
- `python demos/meta_review/demo_pages_manage_metadata.py`
- `python demos/meta_review/demo_pages_read_engagement.py`
- `python demos/meta_review/demo_pages_show_list.py`

Notes:
- These scripts are demo helpers, not part of the production polling pipeline.
- They use the same local `.env` and `polaris.db` context as the rest of the repo.
