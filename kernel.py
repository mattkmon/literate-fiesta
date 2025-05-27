### Fill in the following information before submitting
# Group id: 10
# Members: Nathan Chow, Sean Vu, Matthew Monahan

from collections import deque

# PID is just an integer, but it is used to make it clear when a integer is expected to be a valid PID.
PID = int

# This class represents the PCB of processes.
# It is only here for your convinience and can be modified however you see fit.
class PCB:
    pid: PID
    priority: int

    def __init__(self, pid: PID, priority: int = 0):
        self.pid = pid
        self.priority = priority

# This class represents the Kernel of the simulation.
# The simulator will create an instance of this object and use it to respond to syscalls and interrupts.
# DO NOT modify the name of this class or remove it.
class Kernel:
    def __init__(self, scheduling_algorithm: str, logger):
        self.scheduling_algorithm = scheduling_algorithm
        self.ready_queue = deque()
        self.waiting_queue = deque()
        self.idle_pcb = PCB(0)
        self.running = self.idle_pcb
        self.logger = logger

        self.quantum = 40
        self.time_used = 0
        self.foreground_queue = deque()
        self.background_queue = deque()
        self.is_foreground_level = True
        self.level_time = 0

    def new_process_arrived(self, new_process: PID, priority: int, process_type: str) -> PID:
        new_pcb = PCB(new_process, priority)

        if self.scheduling_algorithm == "FCFS":
            self.ready_queue.append(new_pcb)
            if self.running == self.idle_pcb:
                self.running = self.ready_queue.popleft()

        elif self.scheduling_algorithm == "Priority":
            if (self.running == self.idle_pcb or 
                new_pcb.priority < self.running.priority or
                (new_pcb.priority == self.running.priority and new_pcb.pid < self.running.pid)):
                if self.running != self.idle_pcb:
                    self.ready_queue.append(self.running)
                self.running = new_pcb
            else:
                self.ready_queue.append(new_pcb)

        elif self.scheduling_algorithm == "RR":
            self.ready_queue.append(new_pcb)
            if self.running == self.idle_pcb:
                self.running = self.ready_queue.popleft()
                self.time_used = 0

        elif self.scheduling_algorithm == "Multilevel":
            if process_type == "Foreground":
                self.foreground_queue.append(new_pcb)
            else:
                self.background_queue.append(new_pcb)

            if self.running == self.idle_pcb:
                if self.is_foreground_level and self.foreground_queue:
                    self.running = self.foreground_queue.popleft()
                elif self.background_queue:
                    self.running = self.background_queue.popleft()
                self.time_used = 0
                self.level_time = 0

        return self.running.pid

    def syscall_exit(self) -> PID:
        self.running = self.choose_next_process()
        return self.running.pid

    def syscall_set_priority(self, new_priority: int) -> PID:
        self.running.priority = new_priority

        if self.scheduling_algorithm == "Priority" and self.ready_queue: 
            highest_priority = min(
                self.ready_queue, 
                key=lambda pcb: (pcb.priority, pcb.pid)
            )
            if (highest_priority.priority < self.running.priority or 
                (highest_priority.priority == self.running.priority and highest_priority.pid < self.running.pid)):
                self.ready_queue.remove(highest_priority)
                self.ready_queue.append(self.running)
                self.running = highest_priority

        return self.running.pid

    def choose_next_process(self):
        if self.scheduling_algorithm == "FCFS":
            if self.ready_queue:
                return self.ready_queue.popleft()
        elif self.scheduling_algorithm == "Priority":
            if self.ready_queue:
                highest_priority = min(self.ready_queue, key=lambda pcb: (pcb.priority, pcb.pid))
                self.ready_queue.remove(highest_priority)
                return highest_priority
        elif self.scheduling_algorithm == "RR":
            if self.ready_queue:
                return self.ready_queue.popleft()
        elif self.scheduling_algorithm == "Multilevel":
            if self.is_foreground_level and self.foreground_queue:
                return self.foreground_queue.popleft()
            elif not self.is_foreground_level and self.background_queue:
                return self.background_queue.popleft()
        return self.idle_pcb

    def syscall_init_semaphore(self, semaphore_id: int, initial_value: int):
        return

    def syscall_semaphore_p(self, semaphore_id: int) -> PID:
        return self.running.pid

    def syscall_semaphore_v(self, semaphore_id: int) -> PID:
        return self.running.pid

    def syscall_init_mutex(self, mutex_id: int):
        return

    def syscall_mutex_lock(self, mutex_id: int) -> PID:
        return self.running.pid

    def syscall_mutex_unlock(self, mutex_id: int) -> PID:
        return self.running.pid

    def timer_interrupt(self) -> PID:
        if self.scheduling_algorithm == "RR":
            self.time_used += 10
            if self.time_used >= self.quantum and self.running != self.idle_pcb:
                self.ready_queue.append(self.running)
                self.running = self.ready_queue.popleft() if self.ready_queue else self.idle_pcb
                self.time_used = 0

        elif self.scheduling_algorithm == "Multilevel":
            self.level_time += 10

            if self.is_foreground_level:
                self.time_used += 10
                if self.running == self.idle_pcb and self.foreground_queue:
                    self.running = self.foreground_queue.popleft()
                    self.time_used = 0
                elif self.time_used >= self.quantum and self.running != self.idle_pcb:
                    self.foreground_queue.append(self.running)
                    self.running = self.foreground_queue.popleft() if self.foreground_queue else self.idle_pcb
                    self.time_used = 0
            else:
                if self.running == self.idle_pcb and self.background_queue:
                    self.running = self.background_queue.popleft()

            if self.level_time >= 200:
                self.level_time = 0
                if (self.is_foreground_level and self.background_queue) or (not self.is_foreground_level and self.foreground_queue):
                    self.is_foreground_level = not self.is_foreground_level
                    if self.is_foreground_level and self.foreground_queue:
                        self.running = self.foreground_queue.popleft()
                    elif not self.is_foreground_level and self.background_queue:
                        self.running = self.background_queue.popleft()
                    else:
                        self.running = self.idle_pcb
                    self.time_used = 0

        return self.running.pid
