from models.discussion import Discussion
from models.event import Event


def _make_event(event_type: str, payload: dict) -> Event:
    return Event.from_api(
        {
            "id": "evt-1",
            "type": event_type,
            "actor": {"id": 1, "login": "alice", "avatar_url": ""},
            "repo": {"id": 10, "name": "owner/repo", "url": ""},
            "payload": payload,
            "public": True,
            "created_at": "2026-02-16T11:15:00Z",
        }
    )


def _discussion_comment_node(comment_id: str, author_login: str, body: str) -> dict:
    return {
        "id": comment_id,
        "databaseId": 1,
        "body": body,
        "url": f"https://example.com/{comment_id}",
        "createdAt": "2026-02-16T10:00:00Z",
        "updatedAt": "2026-02-16T10:00:00Z",
        "author": {"login": author_login, "databaseId": 1, "avatarUrl": ""},
    }


def test_discussion_comment_reply_event_wording():
    event = _make_event(
        "DiscussionCommentEvent",
        {
            "action": "created",
            "discussion": {"number": 8359, "title": "I CANNOT CONNECT"},
            "comment": {"in_reply_to_id": "abc123"},
        },
    )
    assert event.get_action_description() == "replied in discussion #8359: I CANNOT CONNECT"


def test_flatten_discussion_comments_includes_replies_and_parent_login():
    top = _discussion_comment_node("c1", "top_author", "Top-level comment")
    reply = _discussion_comment_node("r1", "reply_author", "Reply text")
    top["replies"] = {"nodes": [reply]}

    flattened = Discussion._flatten_comment_nodes([top])

    assert len(flattened) == 2
    assert flattened[0].is_reply is False
    assert flattened[0].author.login == "top_author"
    assert flattened[1].is_reply is True
    assert flattened[1].author.login == "reply_author"
    assert flattened[1].parent_author_login == "top_author"


def test_discussion_from_graphql_flattens_replies():
    top = _discussion_comment_node("c1", "top_author", "Top-level comment")
    reply = _discussion_comment_node("r1", "reply_author", "Reply text")
    top["replies"] = {"nodes": [reply]}

    discussion = Discussion.from_graphql(
        {
            "id": "d1",
            "number": 8359,
            "title": "Connection issues",
            "body": "Body",
            "author": {"login": "author", "databaseId": 1, "avatarUrl": ""},
            "category": {"name": "Help"},
            "isAnswered": False,
            "createdAt": "2026-02-16T09:00:00Z",
            "updatedAt": "2026-02-16T09:00:00Z",
            "url": "https://github.com/owner/repo/discussions/8359",
            "comments": {
                "totalCount": 1,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [top],
            },
        }
    )

    assert len(discussion.comments) == 2
    assert discussion.comments[1].is_reply is True
    assert discussion.comments[1].parent_author_login == "top_author"
