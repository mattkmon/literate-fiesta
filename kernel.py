### Fill in the following information before submitting
# Group id: 10
# Members: Nathan Chow, Sean Vu, Matthew Monahan

from collections import deque

# PID is just an integer, but it is used to make it clear when a integer is expected to be a valid PID.
PID = int

# This class represents the MMU of the simulation.
# The simulator will create an instance of this object and use it to translate memory accesses.
# DO NOT modify the name of this class or remove it.
class MMU:
	# Called before the simulation begins (even before kernel __init__).
	# Use this function to initialize any variables you need throughout the simulation.
	# DO NOT rename or delete this method. DO NOT change its arguments.
    def __init__(self, logger):
        self.process_segments = {}  # imageine (v_start, p_start, offset)
        self.logger = logger

    # Translate the virtual address to its physical address.
	# If it is not a valid address for the given process, return None which will cause a segmentation fault.
	# If it is valid, translate the given virtual address to its physical address.
	# DO NOT rename or delete this method. DO NOT change its arguments.
    def translate(self, address: int, pid: PID) -> int | None:
        if pid not in self.process_segments:
            return None
        
        v_start, p_start, size = self.process_segments[pid]
    
        if address < v_start or address >= v_start + size:
            return None
        
        offset = address - v_start
        return p_start + offset
    
    def allocate_mem_segment(self, pid: PID, p_start: int, size: int):
        v_start = 0x20000000
        self.process_segments[pid] = (v_start, p_start, size)
    
    def deallocate_mem_segment(self, pid: PID):
        if pid in self.process_segments:
            del self.process_segments[pid]

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
    
    # Called before the simulation begins.
    # Use this function to initilize any variables you need throughout the simulation.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def __init__(self, scheduling_algorithm: str, logger, mmu: "MMU", memory_size: int):
        self.scheduling_algorithm = scheduling_algorithm
        self.ready_queue = deque()
        self.waiting_queue = deque()
        self.idle_pcb = PCB(0)
        self.running = self.idle_pcb
        self.logger = logger
        self.mmu = mmu
        self.memory_size = memory_size

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
        
        self.kernel_reserved_bytes = 10485760
        self.available_holes = [(self.kernel_reserved_bytes, memory_size - self.kernel_reserved_bytes)]
        self.allocated_segments = {}

    def _find_best_fit(self, memory_needed: int) -> int | None:
        best_hole = None
        best_index = -1
        
        for i, (start, size) in enumerate(self.available_holes):
            if size >= memory_needed:
                if best_hole is None or size < best_hole[1] or (size == best_hole[1] and start < best_hole[0]):
                    best_hole = (start, size)
                    best_index = i
        
        if best_hole is None:
            return None
        
        start, size = best_hole
        self.available_holes.pop(best_index)
        
        if size > memory_needed:
            remaining_start = start + memory_needed
            remaining_size = size - memory_needed
            self.available_holes.append((remaining_start, remaining_size))
            self.available_holes.sort(key=lambda x: x[0])
        
        return start

    def _free_memory(self, pid: PID):
        if pid not in self.allocated_segments:
            return
        
        start, size = self.allocated_segments[pid]
        del self.allocated_segments[pid]
        
        self.available_holes.append((start, size))
        self.available_holes.sort(key=lambda x: x[0])
        
        merged_holes = []
        for start, size in self.available_holes:
            if merged_holes and merged_holes[-1][0] + merged_holes[-1][1] == start:
                prev_start, prev_size = merged_holes[-1]
                merged_holes[-1] = (prev_start, prev_size + size)
            else:
                merged_holes.append((start, size))
        
        self.available_holes = merged_holes

    # This method is triggered every time a new process has arrived.
    # new_process is this process's PID.
    # priority is the priority of new_process.
    # DO NOT rename or delete this method. DO NOT change its arguments.
    def new_process_arrived(self, new_process: PID, priority: int, process_type: str, memory_needed: int = 0) -> PID:
        if memory_needed > 0:
            p_start = self._find_best_fit(memory_needed)
            if p_start is None: 
                return -1 # no space
            self.allocated_segments[new_process] = (p_start, memory_needed)
            self.mmu.allocate_mem_segment(new_process, p_start, memory_needed)
        
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
        self._free_memory(self.running.pid)
        self.mmu.deallocate_mem_segment(self.running.pid)
        
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
