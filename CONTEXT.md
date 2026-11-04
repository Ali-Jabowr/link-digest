# Link Digest

Turns links saved to one private Telegram group into reports that replace reading or watching the original. The group has a single member who posts: its owner.

## Language

**Link**:
A URL found in a message in the group, whether visible in the text or hidden behind a word.
_Avoid_: Bookmark, item

**Source**:
The content read from a Link, split into Segments: a video transcript or an article.
_Avoid_: Document, input

**Segment**:
One citable piece of a Source: a timestamped stretch of a video, or a numbered paragraph of an article.
_Avoid_: Chunk, line

**Report**:
The written document made from a Source, in which every point cites a Segment.
_Avoid_: Note, summary

**Digest**:
The finished result for a Link: its Report, a short summary, and its citation counts.
_Avoid_: Output, result

**Delivery**:
Sending a finished Digest to the group. A failed Delivery never causes a new Digest to be made.
_Avoid_: Reply, send

**Job**:
The tracked work for one Link: first its Digest, then its Delivery.
_Avoid_: Task

**Thread**:
A chain of posts by one author, read as a single Source whichever of its posts was linked. Other people's replies are not part of it.
_Avoid_: Conversation

**Wrapper post**:
A short post with exactly one Link, whose only value is that Link, so the Digest is made from the linked page instead.
_Avoid_: Link post

**Import**:
Queuing Links from a Telegram Desktop export of the group, to recover ones the bot never saw.
_Avoid_: Sync, backfill
