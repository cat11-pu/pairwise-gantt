"""gantt.core 的验收测试。

只描述期望行为，覆盖拓扑序、最早与最晚开始、总松弛与关键链、并行上限、里程碑、
成环报错与非法输入。
"""

import unittest

from gantt import (
    GanttError,
    Task,
    critical_path,
    project_length,
    schedule,
    topological_order,
)


def task(name, duration, deps=(), milestone=False):
    """构造一个任务描述。"""
    return Task(name, duration, deps, milestone)


def durations(specs):
    """任务名到工期的映射。"""
    return {spec.name: spec.duration for spec in specs}


class TopologyTests(unittest.TestCase):

    def test_topological_order_is_name_sorted_and_registration_independent(self):
        flat = [task("zulu", 1), task("alpha", 1), task("mike", 1),
                task("kilo", 1)]
        self.assertEqual(topological_order(flat),
                         ("alpha", "kilo", "mike", "zulu"))
        shuffled = [task("mike", 1), task("kilo", 1), task("zulu", 1),
                    task("alpha", 1)]
        self.assertEqual(topological_order(shuffled),
                         ("alpha", "kilo", "mike", "zulu"))

        graph = [task("ship", 2, deps=("build",)), task("build", 3),
                 task("test", 1, deps=("build",)), task("plan", 1)]
        self.assertEqual(topological_order(graph),
                         ("build", "plan", "ship", "test"))
        self.assertEqual(topological_order([]), ())


class CycleTests(unittest.TestCase):

    def test_cycles_are_reported_as_gantt_error(self):
        ring = [task("a", 2, deps=("c",)), task("b", 1, deps=("a",)),
                task("c", 1, deps=("b",))]
        self.assertRaises(GanttError, topological_order, ring)
        self.assertRaises(GanttError, topological_order,
                          [task("solo", 1, deps=("solo",)), task("free", 1)])
        self.assertRaises(GanttError, topological_order,
                          ring + [task("free", 1)])
        self.assertTrue(issubclass(GanttError, ValueError))


class TimingTests(unittest.TestCase):

    def test_dependency_completion_gates_the_start(self):
        chain = [task("design", 2), task("build", 3, deps=("design",)),
                 task("ship", 1, deps=("build",))]
        result = schedule(chain)
        self.assertEqual(result.starts,
                         {"design": 0, "build": 2, "ship": 5})
        self.assertEqual(result.finishes,
                         {"design": 2, "build": 5, "ship": 6})
        self.assertEqual(result.horizon, 6)
        self.assertEqual(project_length(chain), 6)
        for spec in chain:
            for dep in spec.deps:
                self.assertLessEqual(result.finishes[dep],
                                     result.starts[spec.name])


class SlackTests(unittest.TestCase):

    def test_slack_and_critical_use_every_successor(self):
        specs = [task("kickoff", 0, milestone=True),
                 task("draft", 2, deps=("kickoff",)),
                 task("review", 5, deps=("kickoff",))]
        result = schedule(specs)
        self.assertEqual(result.horizon, 5)
        self.assertEqual(result.starts["kickoff"], 0)
        self.assertEqual(result.finishes["kickoff"], 0)
        self.assertEqual(result.slack["draft"], 3)
        self.assertEqual(result.slack["review"], 0)
        self.assertEqual(result.slack["kickoff"], 0)
        self.assertEqual(result.critical, ("kickoff", "review"))
        self.assertTrue(result.is_critical("review"))
        self.assertFalse(result.is_critical("draft"))


class ResourceTests(unittest.TestCase):

    def test_parallel_capacity_is_respected_and_slots_are_filled(self):
        jobs = [task("a", 1), task("b", 1), task("c", 1), task("d", 1)]
        result = schedule(jobs, capacity=2)
        self.assertEqual(result.capacity, 2)
        self.assertLessEqual(result.peak, 2)
        self.assertEqual(result.peak, 2)
        self.assertEqual(result.horizon, 2)
        self.assertEqual(sorted(result.starts.values()), [0, 0, 1, 1])

    def test_peak_ignores_intervals_that_only_touch(self):
        link = [task("first", 2), task("second", 2, deps=("first",))]
        result = schedule(link, capacity=2)
        self.assertEqual(result.starts["first"], 0)
        self.assertEqual(result.starts["second"], 2)
        self.assertEqual(result.finishes["second"], 4)
        self.assertEqual(result.horizon, 4)
        self.assertEqual(result.peak, 1)
        self.assertEqual(schedule([task("solo", 3)]).peak, 1)


class MilestoneTests(unittest.TestCase):

    def test_milestone_takes_no_slot_and_gates_its_dependents(self):
        specs = [task("gate", 0, milestone=True),
                 task("alpha", 1, deps=("gate",)),
                 task("beta", 1, deps=("gate",))]
        result = schedule(specs, capacity=1)
        self.assertEqual(result.starts["gate"], 0)
        self.assertEqual(result.finishes["gate"], 0)
        self.assertEqual(sorted(result.starts.values()), [0, 0, 1])
        self.assertEqual(result.horizon, 2)


class CriticalPathTests(unittest.TestCase):

    def test_critical_path_is_a_longest_chain_with_stable_ties(self):
        first = critical_path([task("beta", 2), task("alpha", 2)])
        second = critical_path([task("alpha", 2), task("beta", 2)])
        self.assertEqual(first, ("alpha",))
        self.assertEqual(second, ("alpha",))

        chain = [task("big", 4), task("later", 1, deps=("big",))]
        self.assertEqual(critical_path(chain), ("big", "later"))
        self.assertEqual(project_length(chain), 5)

        rooted = [task("m", 0, milestone=True),
                  task("wide", 4, deps=("m",)),
                  task("narrow", 2, deps=("m",))]
        self.assertEqual(critical_path(rooted), ("m", "wide"))


class ValidationTests(unittest.TestCase):

    def test_invalid_input_is_rejected(self):
        self.assertRaises(ValueError, task, "a", 0)
        self.assertRaises(ValueError, task, "a", -1)
        self.assertRaises(ValueError, task, "a", 2, (), True)
        self.assertRaises(ValueError, task, "", 1)
        self.assertRaises(ValueError, task, "a", 1, ("a", "a"))
        self.assertRaises(TypeError, task, "a", 1.5)
        self.assertRaises(TypeError, task, "a", True)

        self.assertRaises(GanttError, topological_order,
                          [task("a", 1, deps=("ghost",))])
        self.assertRaises(GanttError, topological_order,
                          [task("a", 1), task("a", 2)])
        self.assertRaises(TypeError, schedule, [object()])
        self.assertRaises(ValueError, schedule, [task("a", 1)], 0)
        self.assertRaises(TypeError, schedule, [task("a", 1)], 2.5)

        self.assertEqual(schedule([]).horizon, 0)
        self.assertEqual(schedule([]).critical, ())
        self.assertEqual(project_length([]), 0)
        self.assertEqual(critical_path([]), ())


class ProjectTests(unittest.TestCase):

    def test_project_invariants_end_to_end(self):
        specs = [task("spec", 2), task("design", 3, deps=("spec",)),
                 task("code", 4, deps=("design",)),
                 task("docs", 1, deps=("design",)),
                 task("ship", 1, deps=("code", "docs"))]
        result = schedule(specs)
        length = project_length(specs)
        self.assertEqual(length, 10)
        self.assertEqual(result.horizon, length)

        known = durations(specs)
        path = critical_path(specs)
        self.assertEqual(sum(known[name] for name in path), length)
        self.assertEqual(set(result.critical),
                         {"spec", "design", "code", "ship"})
        self.assertEqual(result.slack["docs"], 3)
        for value in result.slack.values():
            self.assertGreaterEqual(value, 0)
        for spec in specs:
            for dep in spec.deps:
                self.assertLessEqual(result.finishes[dep],
                                     result.starts[spec.name])

        limited = schedule(specs, capacity=2)
        self.assertLessEqual(limited.peak, 2)
        self.assertGreaterEqual(limited.horizon, length)
        for spec in specs:
            for dep in spec.deps:
                self.assertLessEqual(limited.finishes[dep],
                                     limited.starts[spec.name])


if __name__ == "__main__":
    unittest.main()
