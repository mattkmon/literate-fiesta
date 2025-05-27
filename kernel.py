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
    process_type: str

    def __init__(self, pid: PID, priority: int = 0, process_type: str = "Foreground"):
        self.pid = pid
        self.priority = priority
        self.process_type = process_type
        self._saved_quantum = None

# This class represents the Kernel of the simulation.
# The simulator will create an instance of this object and use it to respond to syscalls and interrupts.
# DO NOT modify the name of this class or remove it.
class Kernel:
    scheduling_algorithm: str
    ready_queue: deque[PCB]
    waiting_queue: deque[PCB]
    running: PCB
    idle_pcb: PCB

    def __init__(self, scheduling_algorithm: str, logger):
        self.scheduling_algorithm = scheduling_algorithm
        self.ready_queue = deque()
        self.waiting_queue = deque()
        self.idle_pcb = PCB(0)
        self.running = self.idle_pcb
        self.logger = logger

        self.quantum = 40
        self.time = 0
        self.semaphores = {}
        self.mutexes = {}
        
        # new variables for Multilevel Scheduling
        self.foreground_queue = deque()  
        self.background_queue = deque()
        self.current_queue = "foreground" # switch between foreground and background
        self.queue_switch_time = 0 
        self.rr_time = 0
        self.rr_remaining_time = 0
        self.process_start_time = 0  # Track when current process started running

    # This method is triggered every time a new process has arrived.
    # new_process is this process's PID.
    # priority is the priority of new_process.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def new_process_arrived(self, new_process: PID, priority: int, process_type: str) -> PID:
        new_pcb = PCB(new_process, priority, process_type)

        if self.scheduling_algorithm == "FCFS":
            self.ready_queue.append(new_pcb)
            if self.running == self.idle_pcb:
                next_process = self.ready_queue.popleft()
                self.running = next_process

        elif self.scheduling_algorithm == "Priority":
            if (self.running == self.idle_pcb or 
                new_pcb.priority < self.running.priority or (new_pcb.priority == self.running.priority and new_pcb.pid < self.running.pid)):

                if self.running != self.idle_pcb:
                    self.ready_queue.append(self.running)
                self.running = new_pcb
            else:
                self.ready_queue.append(new_pcb)

        elif self.scheduling_algorithm == "RR":
            self.ready_queue.append(new_pcb)
            if self.running == self.idle_pcb:
                self.running = self.ready_queue.popleft()
                self.time = 0
                
            # video note: if a process switches between interrupts, system assumes it has run for 10ms even if it started to first timer interrupt, 
            # switch -> interrupt = 10 ms
            # 50 % of time is spent in Foreground Queue (RR), 50 % in Background Queue (FCFS)
            # swap every 200ms commit.
            # only swap if there is a process in the opposite queue, else commit 
            # last edge case: when we switch off Foreground, pause the RR and do no reset it. 
            # check the last task from RR 40ms Time quantam each, and see the remaining time
            
            # theres 2 queues: Foreground (RR) and Background (FCFS)
        elif self.scheduling_algorithm == "Multilevel":
            if process_type == "Foreground":
                self.foreground_queue.append(new_pcb)
            else:
                self.background_queue.append(new_pcb)
            if self.running == self.idle_pcb:
                self.running = self._choose_next_process_multilevel()
                if self.running != self.idle_pcb:
                    self.time = 0
                    self.queue_switch_time = 0
                    self.process_start_time = 0
                    if self.running.process_type == "Foreground":
                        self.current_queue = "foreground"
                        self.rr_remaining_time = self.quantum
                    else:
                        self.current_queue = "background"

        return self.running.pid

    # This method is triggered every time the current process performs an exit syscall.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_exit(self) -> PID:
        if self.scheduling_algorithm == "Multilevel":
            exit_time = self.rr_time
            self.running = self._choose_next_process_multilevel()
            
            self.process_start_time = exit_time
        else:
            self.running = self.choose_next_process()
        
        return self.running.pid

    # This method is triggered when the currently running process requests to change its priority.
    # DO NOT rename or delete this method. DO NOT change its arguments.
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
    
    # custom helper function for multilevel scheduling
    def _choose_next_process_multilevel(self):
        if self.current_queue == "foreground" and len(self.foreground_queue) > 0:
            selected = self.foreground_queue.popleft()
            if selected._saved_quantum is not None:
                self.rr_remaining_time = selected._saved_quantum
                selected._saved_quantum = None
            else:
                self.rr_remaining_time = self.quantum
            return selected
        elif self.current_queue == "background" and len(self.background_queue) > 0:
            return self.background_queue.popleft()
        elif len(self.foreground_queue) > 0:
            self.current_queue = "foreground"
            self.queue_switch_time = 0
            selected = self.foreground_queue.popleft()
            if selected._saved_quantum is not None:
                self.rr_remaining_time = selected._saved_quantum
                selected._saved_quantum = None
            else:
                self.rr_remaining_time = self.quantum
            return selected
        elif len(self.background_queue) > 0:
            self.current_queue = "background"
            self.queue_switch_time = 0
            return self.background_queue.popleft()

        return self.idle_pcb

    # This is where you can select the next process to run.
    # This method is not directly called by the simulator and is purely for your convinience.
    # Feel free to modify this method as you see fit.
    # It is not required to actually use this method but it is recommended.
    def choose_next_process(self):
        if self.scheduling_algorithm == "Multilevel":
            return self._choose_next_process_multilevel()
        if len(self.ready_queue) == 0:
            return self.idle_pcb
        if self.scheduling_algorithm == "FCFS":
            return self.ready_queue.popleft()
        elif self.scheduling_algorithm == "Priority":
            highest_priority = min(
                self.ready_queue, 
                key=lambda pcb: (pcb.priority, pcb.pid)
            )
            self.ready_queue.remove(highest_priority)
            return highest_priority
        elif self.scheduling_algorithm == "RR":
            selected = self.ready_queue.popleft()
            self.time = 0
            return selected
        return self.idle_pcb

    # This method is triggered when the currently running process requests to initialize a new semaphore.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_init_semaphore(self, semaphore_id: int, initial_value: int):
        self.semaphores[semaphore_id] = {"value": initial_value, "queue": deque()}

    # This method is triggered when the currently running process calls p() on an existing semaphore.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_semaphore_p(self, semaphore_id: int) -> PID:
        sem = self.semaphores[semaphore_id]
        if sem["value"] > 0:
            sem["value"] -= 1
        else:
            sem["queue"].append(self.running)
            self.running = self.choose_next_process()
            if self.scheduling_algorithm == "RR":
                self.time = 0
        return self.running.pid

    # This method is triggered when the currently running process calls v() on an existing semaphore.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_semaphore_v(self, semaphore_id: int) -> PID:
        sem = self.semaphores[semaphore_id]
        if sem["queue"]:
            if self.scheduling_algorithm == "Priority":
                proc = min(sem["queue"], key=lambda pcb: (pcb.priority, pcb.pid))
                sem["queue"].remove(proc)
            else:
                proc = min(sem["queue"], key=lambda pcb: pcb.pid)
                sem["queue"].remove(proc)
        
            if self.scheduling_algorithm == "Multilevel":
                if proc.process_type == "Foreground":
                    self.foreground_queue.append(proc)
                else:
                    self.background_queue.append(proc)
            else:
                self.ready_queue.append(proc)
        else:
            sem["value"] += 1
        return self.running.pid

    # This method is triggered when the currently running process requests to initialize a new mutex.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_init_mutex(self, mutex_id: int):
        self.mutexes[mutex_id] = {"locked": False, "owner": None, "queue": deque()}

    # This method is triggered when the currently running process calls lock() on an existing mutex.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_mutex_lock(self, mutex_id: int) -> PID:
        mtx = self.mutexes[mutex_id]
        if not mtx["locked"]:
            mtx["locked"] = True
            mtx["owner"] = self.running
        else:
            mtx["queue"].append(self.running)
            self.running = self.choose_next_process()
            if self.scheduling_algorithm == "RR":
                self.time = 0
        return self.running.pid

    # This method is triggered when the currently running process calls unlock() on an existing mutex.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def syscall_mutex_unlock(self, mutex_id: int) -> PID:
        mtx = self.mutexes[mutex_id]
        if mtx["owner"] == self.running:
            if mtx["queue"]:
                if self.scheduling_algorithm == "Priority":
                    proc = min(mtx["queue"], key=lambda pcb: (pcb.priority, pcb.pid))
                    mtx["queue"].remove(proc)
                else:
                    proc = min(mtx["queue"], key=lambda pcb: pcb.pid)
                    mtx["queue"].remove(proc)
                mtx["owner"] = proc
                
                if self.scheduling_algorithm == "Multilevel":
                    if proc.process_type == "Foreground":
                        self.foreground_queue.append(proc)
                    else:
                        self.background_queue.append(proc)
                else:
                    self.ready_queue.append(proc)
            else:
                mtx["locked"] = False
                mtx["owner"] = None
        return self.running.pid

    # This function represents the hardware timer interrupt.
    # It is triggered every 10 microseconds and is the only way a kernel can track passing time.
    # Do not use real time to track how much time has passed as time is simulated.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def timer_interrupt(self) -> PID:
        if self.scheduling_algorithm == "RR":
            self.time += 10
            if self.time >= self.quantum and self.running != self.idle_pcb:
                self.ready_queue.append(self.running)
                self.running = self.choose_next_process()
                self.time = 0
        elif self.scheduling_algorithm == "Multilevel":
            self.time += 10
            self.queue_switch_time += 10
            
            need_context_switch = False
            
            if (self.running != self.idle_pcb and 
                self.running.process_type == "Foreground"):
                self.rr_remaining_time -= 10
                
                if self.rr_remaining_time <= 0:
                    self.foreground_queue.append(self.running)
                    need_context_switch = True
            
            if self.queue_switch_time >= 200:
                if self.current_queue == "foreground" and len(self.background_queue) > 0:
                    if (self.running != self.idle_pcb and 
                        self.running.process_type == "Foreground" and
                        not need_context_switch):
                        self.running._saved_quantum = self.rr_remaining_time
                        self.foreground_queue.appendleft(self.running)
                    self.current_queue = "background"
                    need_context_switch = True
                elif self.current_queue == "background" and len(self.foreground_queue) > 0:
                    if (self.running != self.idle_pcb and 
                        self.running.process_type == "Background"):
                        self.background_queue.appendleft(self.running)
                    self.current_queue = "foreground"
                    need_context_switch = True
                self.queue_switch_time = 0

            if need_context_switch:
                self.running = self._choose_next_process_multilevel()
            
        return self.running.pid
