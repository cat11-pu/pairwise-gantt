# gantt

一个只用 Python 标准库实现的任务依赖与关键路径内核实验项目。
时间按整数刻度推进，不使用真实时钟、线程、网络或随机数，同样的输入永远得到同样的输出。

## 模块内容

`gantt/core.py` 提供：

- `Task(name, duration, deps=(), milestone=False)`：一个任务。`duration` 是工期，`deps` 是一组前置任务名，
  `milestone=True` 表示里程碑，它的工期必须是 0，普通任务的工期必须为正。
- `GanttError(ValueError)`：依赖成环、依赖缺失或参数不合法时抛出。
- `topological_order(tasks)`：依赖的拓扑序，返回任务名元组；同时就绪的任务按任务名字典序，成环时抛 `GanttError`。
- `project_length(tasks)`：工期下界，也就是最长依赖链的长度。
- `critical_path(tasks)`：一条最长依赖链，从最早的任务排到最晚的任务。
- `schedule(tasks, capacity=None)`：排程，返回 `Schedule`。

## 排程的语义

- 最早开始：所有前置任务最早完成的较大者，没有前置就从 0 开始；最早完成等于最早开始加工期。
  任何任务的开始时刻都不早于它每个前置任务的完成时刻。
- 工期下界取所有任务最早完成的最大值；不限并行时它同时也是最短工期。
- 最晚开始按逆拓扑序回推：没有后继的任务以工期下界为最晚完成，有后继的任务取所有后继最晚开始的最小值，
  再减掉自己的工期。
- 总松弛等于最晚开始减最早开始，恒不为负；总松弛为 0 的任务是关键时刻任务，`Schedule.critical` 按拓扑序给出它们。
  `critical_path` 给出其中一条链，链上各任务工期之和等于工期下界。
- 终点与回溯的并列都按任务名字典序取小的那一个，所以同一个依赖图无论按什么顺序注册，结果都一样。
- `capacity=None` 时并行任务数不限；给正整数时同一时刻在跑的作业不超过该数，其余任务顺延，同一时刻能放行
  几个就放行几个，`capacity` 必须是正整数。里程碑不占名额，它只把时间钉在一个点上。
- `Schedule` 的字段：`starts`、`finishes`、`slack`、`critical`、`order`、`horizon`、`capacity`、`peak`，
  以及 `is_critical(name)`。`peak` 是并行峰值，只有真正重叠的区间才计在一起。

## 目录

```
gantt/__init__.py     对外导出
gantt/core.py         依赖排序、松弛与排程内核
tests/test_core.py    验收测试
```

## 怎么跑测试

在项目根目录执行：

```
python3 -m unittest discover -s tests -v
```

Windows 上用任意 Python 3 解释器执行同一条命令即可，例如：

```
C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe -m unittest discover -s tests -v
```
