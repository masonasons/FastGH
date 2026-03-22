from datetime import datetime, timezone
from models.issue import Comment


def _make_comment_data(comment_id: int = 1, body: str = "A comment") -> dict:
    return {
        "id": comment_id,
        "body": body,
        "user": {"id": 10, "login": "alice", "avatar_url": ""},
        "created_at": "2026-01-01T10:00:00Z",
        "updated_at": "2026-01-01T10:00:00Z",
        "html_url": f"https://github.com/owner/repo/issues/1#issuecomment-{comment_id}",
    }


def test_comment_kind_defaults_to_issue():
    comment = Comment.from_github_api(_make_comment_data())
    assert comment.kind == "issue"


def test_comment_kind_review_is_set():
    comment = Comment.from_github_api(_make_comment_data(), kind="review")
    assert comment.kind == "review"


def test_comment_kind_preserved_on_dataclass():
    comment = Comment.from_github_api(_make_comment_data(comment_id=2), kind="review")
    assert comment.id == 2
    assert comment.body == "A comment"
    assert comment.kind == "review"


def test_pr_comments_merge_sorted_by_created_at():
    """get_pr_comments returns issue + review comments sorted chronologically."""
    issue_data = _make_comment_data(comment_id=1)
    issue_data["created_at"] = "2026-01-01T10:00:00Z"

    review_data = _make_comment_data(comment_id=2)
    review_data["created_at"] = "2026-01-01T09:00:00Z"  # earlier than issue comment

    issue_comment = Comment.from_github_api(issue_data, kind="issue")
    review_comment = Comment.from_github_api(review_data, kind="review")

    merged = sorted(
        [issue_comment, review_comment],
        key=lambda c: c.created_at.timestamp() if c.created_at else 0,
    )

    assert merged[0].kind == "review"
    assert merged[1].kind == "issue"


def test_pr_comments_sort_stable_for_no_created_at():
    """Comments with no created_at sort to front without crashing."""
    data = _make_comment_data()
    data["created_at"] = None
    comment = Comment.from_github_api(data)
    assert comment.created_at is None

    merged = sorted(
        [comment],
        key=lambda c: c.created_at.timestamp() if c.created_at else 0,
    )
    assert len(merged) == 1
