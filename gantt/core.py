"""任务依赖与关键路径内核（纯标准库，行为完全确定）。

任务由 Task 描述：工期为正的作业，或工期为 0 的里程碑；deps 给出前置任务名。
时间以整数刻度表示，不使用真实时钟、线程或网络，同一输入的输出完全一致。

对外接口：

* topological_order() —— 依赖的拓扑序，平级按任务名字典序，成环时抛 GanttError；
* project_length()   —— 工期下界，即最长依赖链的长度；
* critical_path()    —— 一条最长依赖链；
* schedule()         —— 排程，可选并行上限，给出开始、完成、总松弛与关键任务。
"""

__all__ = [
    "GanttError",
    "Schedule",
    "Task",
    "critical_path",
    "project_length",
    "schedule",
    "topological_order",
]


def _require_int(value, label):
    """确认参数是非布尔的整数。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s 必须是整数: %r" % (label, value))
    return value


class GanttError(ValueError):
    """依赖成环、依赖缺失或排程参数不合法。"""


class Task:
    """一个任务：工期为正的作业，或工期为 0 的里程碑。"""

    __slots__ = ("name", "duration", "deps", "milestone")

    def __init__(self, name, duration, deps=(), milestone=False):
        if not isinstance(name, str) or not name:
            raise ValueError("任务名必须是非空字符串: %r" % (name,))
        _require_int(duration, "工期")
        if milestone:
            if duration != 0:
                raise ValueError("里程碑的工期必须为 0: %r" % (duration,))
        elif duration < 1:
            raise ValueError("工期必须为正: %r" % (duration,))
        deps = tuple(deps)
        for dep in deps:
            if not isinstance(dep, str) or not dep:
                raise ValueError("依赖名必须是非空字符串: %r" % (dep,))
        if len(set(deps)) != len(deps):
            raise ValueError("同一依赖不能重复: %r" % (name,))
        self.name = name
        self.duration = duration
        self.deps = deps
        self.milestone = bool(milestone)

    def __repr__(self):
        return "Task(%s, duration=%d, deps=%r)" % (
            self.name, self.duration, self.deps)


class Schedule:
    """一次排程的结果。

    starts / finishes 是任务名到开始与完成时刻的映射，slack 是总松弛，
    critical 是松弛为 0 的任务（按拓扑序），order 是排程用的拓扑序，
    horizon 是工期，capacity 是并行上限（None 表示不限），peak 是并行峰值。
    """

    __slots__ = ("starts", "finishes", "slack", "critical", "order",
                 "horizon", "capacity", "peak")

    def __init__(self, starts, finishes, slack, critical, order, horizon,
                 capacity, peak):
        self.starts = starts
        self.finishes = finishes
        self.slack = slack
        self.critical = critical
        self.order = order
        self.horizon = horizon
        self.capacity = capacity
        self.peak = peak

    def is_critical(self, name):
        """任务是否在关键链上。"""
        return self.slack[name] == 0

    def __repr__(self):
        return "Schedule(horizon=%d, capacity=%r, peak=%d, tasks=%d)" % (
            self.horizon, self.capacity, self.peak, len(self.starts))


def _task_list(tasks):
    """检查任务集，返回任务列表。"""
    specs = list(tasks)
    seen = set()
    for spec in specs:
        if not isinstance(spec, Task):
            raise TypeError("任务集只能包含 Task: %r" % (spec,))
        if spec.name in seen:
            raise GanttError("任务名重复: %r" % (spec.name,))
        seen.add(spec.name)
    for spec in specs:
        for dep in spec.deps:
            if dep not in seen:
                raise GanttError("%s 依赖了不存在的任务 %r" % (spec.name, dep))
    return specs


def _successors(specs):
    """后继表，每个任务的直接后继按任务名升序。"""
    following = {spec.name: [] for spec in specs}
    for spec in specs:
        for dep in spec.deps:
            following[dep].append(spec.name)
    for name in following:
        following[name].sort()
    return following


def topological_order(tasks):
    """依赖的拓扑序；平级任务按任务名字典序，成环时抛 GanttError。"""
    specs = _task_list(tasks)
    following = _successors(specs)
    indegree = {spec.name: len(spec.deps) for spec in specs}
    ready = [name for name, degree in indegree.items() if degree == 0]
    order = []
    while ready:
        name = ready.pop()
        order.append(name)
        for later in following[name]:
            indegree[later] -= 1
            if indegree[later] == 0:
                ready.append(later)
    return tuple(order)


def _forward(specs, order):
    """按拓扑序求最早开始与最早完成。"""
    by_name = {spec.name: spec for spec in specs}
    starts = {}
    finishes = {}
    for name in order:
        spec = by_name[name]
        ready_at = 0
        for dep in spec.deps:
            ready_at = max(ready_at, starts[dep])
        starts[name] = ready_at
        finishes[name] = ready_at + spec.duration
    return starts, finishes


def project_length(tasks):
    """工期下界：最长依赖链的长度，也是不限并行时的最短工期。"""
    specs = _task_list(tasks)
    order = topological_order(specs)
    _, finishes = _forward(specs, order)
    if not finishes:
        return 0
    return max(finishes.values())


def critical_path(tasks):
    """一条最长依赖链，从最早的任务排到最晚的任务。

    终点取最早完成最晚的任务，回溯时取最早完成最晚的前置任务；并列时都按任务名
    字典序取小的那一个。
    """
    specs = _task_list(tasks)
    if not specs:
        return ()
    order = topological_order(specs)
    _, finishes = _forward(specs, order)
    by_name = {spec.name: spec for spec in specs}
    end = max(by_name, key=lambda name: finishes[name])
    chain = [end]
    current = by_name[end]
    while current.deps:
        pick = max(current.deps, key=lambda name: finishes[name])
        chain.append(pick)
        current = by_name[pick]
    chain.reverse()
    return tuple(chain)


def _latest_starts(specs, order, following, horizon):
    """按逆拓扑序求最晚开始：没有后继的任务以工期为最晚完成。"""
    by_name = {spec.name: spec for spec in specs}
    latest = {}
    for name in reversed(order):
        spec = by_name[name]
        later = following[name]
        if later:
            limit = latest[later[0]]
        else:
            limit = horizon
        latest[name] = limit - spec.duration
    return latest


def _resource_plan(specs, order, capacity):
    """在并行上限下按拓扑优先序排程，返回 (开始表, 完成表)。"""
    by_name = {spec.name: spec for spec in specs}
    starts = {}
    finishes = {}
    running = {}
    pending = list(order)
    now = 0
    while pending:
        for name in list(pending):
            spec = by_name[name]
            if any(dep not in finishes or finishes[dep] > now
                   for dep in spec.deps):
                continue
            if spec.duration > 0 and len(running) > capacity:
                continue
            starts[name] = now
            finishes[name] = now + spec.duration
            pending.remove(name)
            if spec.duration > 0:
                running[name] = finishes[name]
            break
        if not pending:
            break
        if running:
            now = min(running.values())
            running = {name: finish for name, finish in running.items()
                       if finish > now}
        else:
            now += 1
    return starts, finishes


def _peak(starts, finishes):
    """任一时刻并行执行的任务数的最大值。"""
    peak = 0
    for name in starts:
        live = 0
        for other in starts:
            if starts[other] <= starts[name] <= finishes[other]:
                live += 1
        peak = max(peak, live)
    return peak


def schedule(tasks, capacity=None):
    """给任务集排程。

    capacity 为 None 时不限制并行任务数，否则任一时刻在跑的作业不超过 capacity
    个，其余任务顺延；里程碑不占名额。总松弛按工期回推，关键任务是松弛为 0 的
    任务，按拓扑序排列。
    """
    specs = _task_list(tasks)
    order = topological_order(specs)
    following = _successors(specs)
    if capacity is None:
        starts, finishes = _forward(specs, order)
    else:
        _require_int(capacity, "并行上限")
        if capacity < 1:
            raise ValueError("并行上限必须为正: %r" % (capacity,))
        starts, finishes = _resource_plan(specs, order, capacity)
    horizon = max(finishes.values()) if finishes else 0
    latest = _latest_starts(specs, order, following, horizon)
    slack = {name: latest[name] - starts[name] for name in order}
    critical = tuple(name for name in order if slack[name] == 0)
    peak = _peak(starts, finishes)
    return Schedule(starts, finishes, slack, critical, order, horizon,
                    capacity, peak)
