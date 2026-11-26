'''
File:   test_llm_sse.py
Brief:  Unit tests for the SSE frame parser.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from collections.abc import AsyncIterator

from mechanic.llm.sse import iter_sse_frames


async def _bytes_chunks(texts: list[str]) -> AsyncIterator[bytes]:
    '''Turn a list of string fragments into an async iterator of UTF-8 bytes.'''
    for t in texts:
        yield t.encode("utf-8")


# ------------------------------------------------------------------
# test_parses_basic_frames
# ------------------------------------------------------------------

async def test_parses_basic_frames():
    '''Feed two chunks splitting mid-line; expect correct event names and data.'''
    # The SSE body:  event: token\ndata: {"a":1}\n\n   (frame 1)
    #               data: x\n\n                         (frame 2)
    # Split the first chunk so "data: {" is in chunk 1 and '}"\n\n...' in chunk 2.
    raw = 'event: token\ndata: {"a":1}\n\ndata: x\n\n'
    split_point = raw.index('{"a":')
    chunks = [raw[:split_point], raw[split_point:]]

    frames = []
    async for frame in iter_sse_frames(_bytes_chunks(chunks)):
        frames.append(frame)

    assert len(frames) == 2
    # Frame 1: event "token", data '{"a":1}'
    assert frames[0][0] == "token"
    assert frames[0][1] == '{"a":1}'
    # Frame 2: event None (no event: line), data "x"
    assert frames[1][0] is None
    assert frames[1][1] == "x"


# ------------------------------------------------------------------
# test_multiline_data_joins_with_newline
# ------------------------------------------------------------------

async def test_multiline_data_joins_with_newline():
    '''Multiple data: lines are joined with \\n per SSE spec.'''
    raw = 'data: hello\ndata: world\n\ndata: foo\n\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)

    assert len(frames) == 2
    assert frames[0][1] == "hello\nworld"
    assert frames[1][1] == "foo"


# ------------------------------------------------------------------
# test_ignores_comments_and_id_retry_fields
# ------------------------------------------------------------------

async def test_ignores_comments_and_id_retry_fields():
    '''Comment lines (:) and id/retry fields are silently dropped.'''
    raw = ': comment line\nid: 123\nretry: 3000\ndata: payload\n\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0][0] is None
    assert frames[0][1] == "payload"


# ------------------------------------------------------------------
# test_flushes_trailing_frame_without_blank_line
# ------------------------------------------------------------------

async def test_flushes_trailing_frame_without_blank_line():
    '''A pending frame at end-of-stream is flushed even without a blank line.'''
    raw = 'event: last\ndata: trailing\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0][0] == "last"
    assert frames[0][1] == "trailing"


# ------------------------------------------------------------------
# test_handles_crlf
# ------------------------------------------------------------------

async def test_handles_crlf():
    '''\\r\\n line endings are handled correctly.'''
    raw = 'event: crlftest\r\ndata: hello world\r\n\r\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0][0] == "crlftest"
    assert frames[0][1] == "hello world"


# ------------------------------------------------------------------
# test_crlf_split_across_chunks
# ------------------------------------------------------------------

async def test_crlf_split_across_chunks():
    '''CRLF split across two byte chunks still parses correctly.'''
    raw = 'event: split\r\ndata: abc\n'
    chunk1 = raw[:12]  # "event: spl"
    chunk2 = raw[12:]  # it\r\ndata: abc\n

    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([chunk1, chunk2])):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0][0] == "split"
    assert frames[0][1] == "abc"


# ------------------------------------------------------------------
# test_no_data_lines_dropped
# ------------------------------------------------------------------

async def test_no_data_lines_dropped():
    '''Frames with no data: lines are dropped.'''
    raw = 'event: named\ndata: has data\n\nevent: empty\n\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0][0] == "named"
    assert frames[0][1] == "has data"


# ------------------------------------------------------------------
# test_empty_stream
# ------------------------------------------------------------------

async def test_empty_stream():
    '''An empty byte stream yields no frames.'''
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([])):
        frames.append(frame)
    assert len(frames) == 0


# ------------------------------------------------------------------
# test_only_comments_yields_nothing
# ------------------------------------------------------------------

async def test_only_comments_yields_nothing():
    '''A stream of only comment lines yields no frames.'''
    raw = ': c1\n: c2\n: c3\n'
    frames = []
    async for frame in iter_sse_frames(_bytes_chunks([raw])):
        frames.append(frame)
    assert len(frames) == 0
