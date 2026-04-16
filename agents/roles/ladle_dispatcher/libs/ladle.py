from src.runtime.lib.decorator import lib_function


class LadleDispatcher:
    """钢包配包调度器：根据钢种、炉次、订单信息获取候选钢包。"""

    def __init__(self):
        # 降级模拟钢包资源池（无外部注入时使用）
        self._fallback_ladles = [
            {
                "ladle_id": "L01",
                "capacity": 300,
                "status": "available",
                "compatible_grades": ["Q235B", "Q345B", "HRB400"],
                "last_grade": None,
                "location": "YD-1",
            },
            {
                "ladle_id": "L02",
                "capacity": 250,
                "status": "available",
                "compatible_grades": ["Q235B", "SS400"],
                "last_grade": "Q235B",
                "location": "YD-2",
            },
            {
                "ladle_id": "L03",
                "capacity": 300,
                "status": "maintenance",
                "compatible_grades": ["Q345B", "HRB400"],
                "last_grade": "HRB400",
                "location": "YD-3",
            },
            {
                "ladle_id": "L04",
                "capacity": 280,
                "status": "available",
                "compatible_grades": ["Q345B", "X70", "Q235B"],
                "last_grade": "Q345B",
                "location": "YD-1",
            },
            {
                "ladle_id": "L05",
                "capacity": 300,
                "status": "available",
                "compatible_grades": ["HRB400", "Q345B"],
                "last_grade": "SS400",
                "location": "YD-2",
            },
        ]

    def _score_ladle(self, ladle: dict, grade: str, tonnage: float) -> float:
        """为钢包打分，分数越高越优先。"""
        score = 0.0

        # 容量越接近需求越好，但必须有富余（5%安全余量）
        capacity = ladle["capacity"]
        if capacity >= tonnage * 1.05:
            score += 10.0
            # 容量匹配度：越接近越优先，避免用大包装小量
            score += max(0, 10 - abs(capacity - tonnage) / 10)
        else:
            # 容量不足，基本淘汰
            score -= 100

        # 上炉钢种相同，优先使用（减少清洗成本）
        if ladle["last_grade"] == grade:
            score += 15.0
        elif ladle["last_grade"] is None:
            # 新包或清洗后，次优先
            score += 8.0
        else:
            # 需要清洗，扣分
            score -= 5.0

        return score

    @lib_function(name="getCandidates", namespace="ladle_dispatcher", readonly=True)
    def get_candidates(self, args: dict) -> dict:
        """
        获取候选钢包列表。

        输入字段：
            - grade: 钢种（如 "Q235B"）
            - heat_id: 炉次号（如 "H2025041401"）
            - order_id: 炉次订单号（如 "ORD-001"）
            - tonnage: 需求吨位（默认 250）
            - top_k: 返回前 K 个候选（默认 3）
        """
        grade = args.get("grade", "")
        heat_id = args.get("heat_id", "")
        order_id = args.get("order_id", "")
        tonnage = float(args.get("tonnage", 250))
        top_k = int(args.get("top_k", 3))

        ladles = args.get("availableLadles") or self._fallback_ladles

        candidates = []
        for ladle in ladles:
            # 规则1：必须可用
            if ladle["status"] != "available":
                continue

            # 规则2：钢种兼容
            if grade not in ladle["compatible_grades"]:
                continue

            # 规则3：容量满足（含5%安全余量）
            if ladle["capacity"] < tonnage * 1.05:
                continue

            score = self._score_ladle(ladle, grade, tonnage)
            candidates.append({
                "ladle_id": ladle["ladle_id"],
                "capacity": ladle["capacity"],
                "location": ladle["location"],
                "last_grade": ladle["last_grade"],
                "score": round(score, 2),
            })

        # 按分数降序排列
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # 截取 top_k
        top_candidates = candidates[:top_k]

        return {
            "heat_id": heat_id,
            "order_id": order_id,
            "grade": grade,
            "tonnage": tonnage,
            "candidates": top_candidates,
            "count": len(top_candidates),
            "total_matched": len(candidates),
        }
