from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.identifiers import Channel, ClientName, FileId, Keyword, NodeId, SourceId


def _node_id(node_id: NodeId) -> str:
    return node_id


def _target_id(target_id: TargetId) -> str:
    return target_id


def _client_name(client_name: ClientName) -> str:
    return client_name


def _channel(channel: Channel) -> str:
    return channel


def _keyword(keyword: Keyword) -> str:
    return keyword


def _file_id(file_id: FileId) -> bytes:
    return file_id


def _source_id(source_id: SourceId) -> bytes:
    return source_id


def test_a_bare_str_is_no_node_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id("node-a") == "node-a"  # type: ignore[arg-type]


def test_a_bare_str_is_no_client_name() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _client_name("amuled") == "amuled"  # type: ignore[arg-type]


def test_a_bare_str_is_no_channel() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _channel("kad") == "kad"  # type: ignore[arg-type]


def test_a_bare_str_is_no_keyword() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _keyword("keroro") == "keroro"  # type: ignore[arg-type]


def test_a_bare_bytes_is_no_file_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _file_id(b"\x00" * 16) == b"\x00" * 16  # type: ignore[arg-type]


def test_a_bare_bytes_is_no_source_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _source_id(b"\x00" * 16) == b"\x00" * 16  # type: ignore[arg-type]


def test_a_node_id_and_a_target_id_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id(TargetId("62a")) == "62a"  # type: ignore[arg-type]
    assert _target_id(NodeId("node-a")) == "node-a"  # type: ignore[arg-type]


def test_a_client_name_and_a_channel_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _client_name(Channel("kad")) == "kad"  # type: ignore[arg-type]
    assert _channel(ClientName("amuled")) == "amuled"  # type: ignore[arg-type]


def test_a_client_name_or_a_channel_is_no_target_id() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _target_id(ClientName("amuled")) == "amuled"  # type: ignore[arg-type]
    assert _target_id(Channel("kad")) == "kad"  # type: ignore[arg-type]


def test_a_keyword_and_a_channel_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _keyword(Channel("kad")) == "kad"  # type: ignore[arg-type]
    assert _channel(Keyword("keroro")) == "keroro"  # type: ignore[arg-type]


def test_a_keyword_is_no_target_id() -> None:
    """The ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _target_id(Keyword("keroro")) == "keroro"  # type: ignore[arg-type]


def test_a_file_id_and_a_source_id_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _file_id(SourceId(b"\x00" * 16)) == b"\x00" * 16  # type: ignore[arg-type]
    assert _source_id(FileId(b"\x00" * 16)) == b"\x00" * 16  # type: ignore[arg-type]


def test_a_node_id_and_a_client_name_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id(ClientName("amuled")) == "amuled"  # type: ignore[arg-type]
    assert _client_name(NodeId("node-a")) == "node-a"  # type: ignore[arg-type]


def test_a_node_id_and_a_channel_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id(Channel("kad")) == "kad"  # type: ignore[arg-type]
    assert _channel(NodeId("node-a")) == "node-a"  # type: ignore[arg-type]


def test_a_node_id_and_a_keyword_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _node_id(Keyword("keroro")) == "keroro"  # type: ignore[arg-type]
    assert _keyword(NodeId("node-a")) == "node-a"  # type: ignore[arg-type]


def test_a_client_name_and_a_keyword_are_refused_for_each_other() -> None:
    """Each ``type: ignore`` proves mypy refuses the call: an unused one fails the gate."""
    assert _client_name(Keyword("keroro")) == "keroro"  # type: ignore[arg-type]
    assert _keyword(ClientName("amuled")) == "amuled"  # type: ignore[arg-type]
