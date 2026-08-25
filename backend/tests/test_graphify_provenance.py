import json

from services.graphify_extractor import GraphifyExtractor


def test_incremental_merge_writes_structured_source_files(tmp_path, monkeypatch):
    user_graph = tmp_path / "user_1_graph.json"
    user_graph.write_text(json.dumps({
        "nodes": [{"id": "shared", "label": "共享实体", "source_file": "a/doc.md"}],
        "links": [],
    }), encoding="utf-8")
    doc_graph = tmp_path / "doc_graph.json"
    doc_graph.write_text(json.dumps({
        "nodes": [{"id": "shared", "label": "共享实体", "source_file": "b/doc.md"}],
        "links": [],
    }), encoding="utf-8")

    monkeypatch.setattr("config.Config.get_user_graph_path", lambda _user_id: str(user_graph))

    GraphifyExtractor()._merge_user_graph_incremental(
        user_id=1,
        doc_id=2,
        extract_result={"graph_path": str(doc_graph)},
    )

    merged = json.loads(user_graph.read_text(encoding="utf-8"))
    node = merged["nodes"][0]
    assert node["source_files"] == ["a/doc.md", "b/doc.md"]
    assert node["source_file"] == "a/doc.md"
