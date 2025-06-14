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
    memory_start: int
    memory_limit: int

    def __init__(self, pid: PID, priority: int = 0, process_type: str = "Foreground"):
        self.pid = pid
        self.priority = priority
        self.process_type = process_type
        self._saved_quantum = None
        self.memory_start = -1
        self.memory_limit = 0

# This class represents the Kernel of the simulation.
# The simulator will create an instance of this object and use it to respond to syscalls and interrupts.
# DO NOT modify the name of this class or remove it.
class Kernel:
    scheduling_algorithm: str
    ready_queue: deque[PCB]
    waiting_queue: deque[PCB]
    running: PCB
    idle_pcb: PCB

    def __init__(self, scheduling_algorithm: str, logger, mmu: "MMU", memory_size: int):
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
        
        self.foreground_queue = deque()  
        self.background_queue = deque()
        self.current_queue = "foreground"
        self.queue_switch_time = 0 
        self.rr_time = 0
        self.rr_remaining_time = 0
        self.process_start_time = 0

        self.mmu = mmu
        self.mmu.kernel = self
        self.memory_size = memory_size
        self.kernel_memory = 10485760
        self.free_memory = [(self.kernel_memory, self.memory_size - self.kernel_memory)]
        self.process_memory = {}

    def new_process_arrived(self, new_process: PID, priority: int, process_type: str, memory_needed: int) -> PID:
        best_fit_hole = None
        for start, size in self.free_memory:
            if size >= memory_needed:
                if best_fit_hole is None or size < best_fit_hole[1]:
                    best_fit_hole = (start, size)
        
        if best_fit_hole is None:
            return -1

        start, size = best_fit_hole
        self.free_memory.remove(best_fit_hole)
        
        if size > memory_needed:
            self.free_memory.append((start + memory_needed, size - memory_needed))
            self.free_memory.sort()

        new_pcb = PCB(new_process, priority, process_type)
        new_pcb.memory_start = start
        new_pcb.memory_limit = memory_needed
        self.process_memory[new_process] = {'start': start, 'limit': memory_needed}


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

    def syscall_exit(self) -> PID:
        exiting_pid = self.running.pid
        if exiting_pid in self.process_memory:
            mem_info = self.process_memory.pop(exiting_pid)
            freed_start, freed_size = mem_info['start'], mem_info['limit']
            
            new_free_memory = []
            merged = False
            for start, size in self.free_memory:
                if start + size == freed_start:
                    freed_start, freed_size = start, size + freed_size
                    merged = True
                elif freed_start + freed_size == start:
                    freed_size += size
                    merged = True
                else:
                    new_free_memory.append((start, size))

            new_free_memory.append((freed_start, freed_size))
            self.free_memory = sorted(new_free_memory)
            
            # Second pass for merging after insertion
            final_free_memory = []
            if self.free_memory:
                current_start, current_size = self.free_memory[0]
                for i in range(1, len(self.free_memory)):
                    next_start, next_size = self.free_memory[i]
                    if current_start + current_size == next_start:
                        current_size += next_size
                    else:
                        final_free_memory.append((current_start, current_size))
                        current_start, current_size = next_start, next_size
                final_free_memory.append((current_start, current_size))
                self.free_memory = final_free_memory


        if self.scheduling_algorithm == "Multilevel":
            exit_time = self.rr_time
            self.running = self._choose_next_process_multilevel()
            self.process_start_time = exit_time
        else:
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

    def syscall_init_semaphore(self, semaphore_id: int, initial_value: int):
        self.semaphores[semaphore_id] = {"value": initial_value, "queue": deque()}

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
                if self.scheduling_algorithm == "Priority":
                    if (proc.priority < self.running.priority or 
                        (proc.priority == self.running.priority and proc.pid < self.running.pid)):
                        self.ready_queue.append(self.running)
                        self.running = proc
                    else:
                        self.ready_queue.append(proc)
                else:
                    self.ready_queue.append(proc)
        else:
            sem["value"] += 1
        return self.running.pid

    def syscall_init_mutex(self, mutex_id: int):
        self.mutexes[mutex_id] = {"locked": False, "owner": None, "queue": deque()}

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
                    if self.scheduling_algorithm == "Priority":
                        if (proc.priority < self.running.priority or 
                            (proc.priority == self.running.priority and proc.pid < self.running.pid)):
                            self.ready_queue.append(self.running)
                            self.running = proc
                        else:
                            self.ready_queue.append(proc)
                    else:
                        self.ready_queue.append(proc)                   
            else:
                mtx["locked"] = False
                mtx["owner"] = None
        return self.running.pid

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

# This class represents the MMU of the simulation.
# The simulator will create an instance of this object and use it to translate memory accesses.
# DO NOT modify the name of this class or remove it.
class MMU:
    def __init__(self, logger):
        self.logger = logger
        self.kernel = None

    def translate(self, address: int, pid: PID) -> int | None:
        virtual_base = 0x20000000
        if address < virtual_base:
            return None

        if pid not in self.kernel.process_memory:
            return None

        mem_info = self.kernel.process_memory[pid]
        physical_base = mem_info['start']
        limit = mem_info['limit']

        offset = address - virtual_base
        if offset >= limit:
            return None
            
        return physical_base + offset
