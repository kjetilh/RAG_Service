import json
from pathlib import Path
from app.rag.pipeline import answer_question

def main():
    eval_path = Path("data/eval/questions.jsonl")
    if not eval_path.exists():
        print("No eval set found at data/eval/questions.jsonl. Create it to run eval.")
        return
    out = []
    for line in eval_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        q = item["question"]
        resp = answer_question(q, conversation_id=None, filters=item.get("filters", {}), top_k=item.get("top_k"))
        out.append({"question": q, "answer": resp.answer, "citations": [c.model_dump() for c in resp.citations]})
    Path("data/eval/results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote data/eval/results.json")

if __name__ == "__main__":
    main()
