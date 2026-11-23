
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

# 1. Load synthetic family notes
file_path = Path(__file__).parent / "family_notes.json"

with open(file_path, "r", encoding="utf-8") as file:
    notes = json.load(file)

# 2. Load a pretrained embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# 3. Convert family notes into embeddings
documents = [
    f"{note['title']}. {note['text']}"
    for note in notes
]

document_embeddings = model.encode(
    documents,
    convert_to_tensor=True
)

# 4. Retrieve the most relevant notes
def retrieve(query, top_k=3):
    query_embedding = model.encode(
        query,
        convert_to_tensor=True
    )

    scores = util.cos_sim(
        query_embedding,
        document_embeddings
    )[0]

    top_results = scores.topk(
        k=min(top_k, len(notes))
    )

    results = []

    for score, index in zip(
        top_results.values,
        top_results.indices
    ):
        note = notes[index.item()]

        results.append({
            "id": note["id"],
            "title": note["title"],
            "text": note["text"],
            "score": round(score.item(), 3)
        })

    return results


# 5. Test semantic retrieval
if __name__ == "__main__":
    query = "How can I reduce driving when running errands?"

    print(f"\nUser query: {query}\n")

    for result in retrieve(query):
        print(f"Title: {result['title']}")
        print(f"Similarity: {result['score']}")
        print(f"Note: {result['text']}\n")
