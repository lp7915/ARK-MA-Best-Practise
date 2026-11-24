# 版本状态机: 预留 in_review(审核), 当前阶段不启用(直接 draft->released 由 API 开关控制)
ALLOWED={
 "draft":      {"candidate","in_review","released","retired"},   # draft 可直接发布(审核未启用时)
 "candidate":  {"in_review","released","draft","retired"},
 "in_review":  {"released","draft","rejected"},                  # 预留
 "rejected":   {"draft","retired"},                              # 预留
 "released":   {"deprecated"},                                   # released 不可回到 draft
 "deprecated": {"released","retired"},                           # 可撤销下线(重新 released), 或最终 retired
 "retired":    set(),
}
REVIEW_ENABLED=False
def can(frm,to):
    if frm==to: return False
    if to=="in_review" and not REVIEW_ENABLED: return False
    if frm=="in_review" and not REVIEW_ENABLED: return False
    if not REVIEW_ENABLED and frm=="rejected": return False
    return to in ALLOWED.get(frm,set())
cases=[("draft","released",True),("draft","candidate",True),("candidate","released",True),("released","draft",False),
       ("released","deprecated",True),("deprecated","released",True),("deprecated","retired",True),("retired","released",False),
       ("draft","in_review",False),("in_review","released",False)]
bad=[(a,b,e,can(a,b)) for a,b,e in cases if can(a,b)!=e]
print("审核未启用: 状态机检查", "全部符合预期" if not bad else bad)
REVIEW_ENABLED=True
print("审核启用后: draft->in_review", can("draft","in_review"), "| in_review->released", can("in_review","released"), "| released->draft", can("released","draft"))
