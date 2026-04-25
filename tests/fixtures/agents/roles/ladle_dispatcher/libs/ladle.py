from src.runtime.lib.decorator import lib_function


class LadleDispatcher:
    def __init__(self):
        self._fallback_ladles = [
            {
                "ladle_id": "L01",
                "capacity": 300,
                "status": "available",
                "compatible_grades": ["Q235B", "Q345B"],
                "last_grade": None,
                "location": "YD-1",
            },
            {
                "ladle_id": "L02",
                "capacity": 280,
                "status": "available",
                "compatible_grades": ["Q235B"],
                "last_grade": "Q235B",
                "location": "YD-2",
            },
        ]

    @lib_function(name="getCandidates", namespace="roles.ladle_dispatcher")
    def get_candidates(self, args: dict) -> dict:
        grade = args.get("grade", "")
        tonnage = float(args.get("tonnage", 250))
        top_k = int(args.get("top_k", 3))

        ladles = args.get("availableLadles") or self._fallback_ladles

        candidates = []
        for ladle in ladles:
            if ladle["status"] != "available":
                continue
            if grade not in ladle["compatible_grades"]:
                continue
            if ladle["capacity"] < tonnage * 1.05:
                continue

            score = 0.0
            if ladle["capacity"] >= tonnage * 1.05:
                score += 10.0
            if ladle["last_grade"] == grade:
                score += 15.0
            elif ladle["last_grade"] is None:
                score += 8.0
            else:
                score -= 5.0

            candidates.append({
                "ladle_id": ladle["ladle_id"],
                "capacity": ladle["capacity"],
                "location": ladle["location"],
                "last_grade": ladle["last_grade"],
                "score": round(score, 2),
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates[:top_k]

        return {
            "heat_id": args.get("heat_id", ""),
            "order_id": args.get("order_id", ""),
            "grade": grade,
            "tonnage": tonnage,
            "candidates": top_candidates,
            "count": len(top_candidates),
            "total_matched": len(candidates),
        }
