import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Usd, Sdf
import os
import glob
import carb
import omni.kit.commands
import omni.kit.viewport
import bisect
import numpy as np
import time

class RGBLiDARVisualizerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("[RGBLiDARVisualizer] Extension started")

        # base dataset path
        self._base_path = "Z:/nuscenes/"
        self._folder_numbers = []
        self._session_identifiers = []
        self._image_timestamps = []
        self._global_sampled_image_timestamps = []
        self._lidar_timestamps = []
        self._global_sampled_lidar_timestamps = []
        self._image_files = []
        self._lidar_files = []
        self._current_image = -9999
        self._current_lidar = -9999
        self._current_folder_number = ""
        self._current_session_identifier = ""
        self._session_changed_fn_id = None

        # define window
        self._window = ui.Window("NuScenes RGB & LiDAR Visualizer", width=400, height=600)
        with self._window.frame:
            with ui.VStack():
                # generate folder numbers -> create folder number select dropdown
                folder_numbers = self.get_folder_numbers()
                

                ui.Label("Select Folder Number:")
                self.folder_number_model: ui.AbstractItemModel = ui.ComboBox(0, *folder_numbers).model
                #self.folder_number_combo = ui.ComboBox(model=self.folder_number_model)
                self.folder_number_model.add_item_changed_fn(self.on_folder_number_changed)
                #for number in folder_numbers:
                #    self.folder_number_combo.model.append_child_item(None, ui.SimpleStringModel(number))
                #print(self.folder_number_model.get_value_as_string())

                # Session Identifier Dropdown
                
                ui.Label("Select Session Identifier:")
                #self.session_identifier_combo = ui.ComboBox(model=self.session_identifier_model)
                self.session_identifier_model: ui.AbstractItemModel = ui.ComboBox(0, *[]).model
                self._session_changed_fn_id = self.session_identifier_model.add_item_changed_fn(self.on_session_identifier_changed)
                #print(self.session_identifier_model.get_value_as_string())

                # Timestamp Slider
                self.timestamp_model = ui.SimpleFloatModel()
                ui.Label("Select Timestamp:")
                self.timestamp_slider = ui.FloatSlider(model=self.timestamp_model, mouse_released_fn=lambda x,y,b,m:self.on_timestamp_changed(), step=1)
                self.timestamp_model.add_value_changed_fn(self.drag_slider)
                # call_mouse_released_fn = call function when mouse released
                #self.timestamp_slider.call_mouse_released_fn(lambda x,y,b,m:self.on_timestamp_changed())
                #print(self.timestamp_model.get_value_as_int())

                # Display Image
                ui.Label("RGB Image:")
                self.image_widget = ui.Image("", width=380, height=280)

                # Instructions
                ui.Label("LiDAR Pointcloud is displayed in the main viewport.", height=20)
                self.folder_number_model.get_item_value_model().set_value("01")
                #self.on_folder_number_changed(self.folder_number_model)

    def on_shutdown(self):
        print("[RGBLiDARVisualizer] Extension shutdown")
        self._window = None

    def get_folder_numbers(self):
        # Get list of folder numbers from the base path
        print("getting folder numbers")
        start_time = time.perf_counter()
        folders = os.listdir(self._base_path)
        print(folders)
        folder_numbers = []
        for folder in folders:
            if folder.startswith("v1.0-trainval") and len(folder) == len("v1.0-trainval00 blobs"):
                folder_numbers.append(folder[-8:-6])
        folder_numbers.sort()
        print(folder_numbers)
        end_time = time.perf_counter()
        print(f"get_folder_numbers execution time: {end_time - start_time} seconds")
        return folder_numbers

    def on_folder_number_changed(self, model, *args):
        start_time = time.perf_counter()
        folder_number = "{0:0=2d}".format(model.get_item_value_model().as_int)#model.get_value_as_string()
        self._current_folder_number = folder_number
        print("folder number changed:", self._current_folder_number)
        
        # Update session identifiers based on folder number
        self._session_identifiers = self.get_session_identifiers(self._current_folder_number)
        #self.session_identifier_model.set_items(self._session_identifiers)
        for item in self.session_identifier_model.get_item_children():
            self.session_identifier_model.remove_item(item)
        #self.session_identifier_model.get_item_children() = [ui.SimpleStringModel(session) for session in self._session_identifiers]
        self.session_identifier_model.remove_item_changed_fn(self._session_changed_fn_id)
        for session in self._session_identifiers:
            self.session_identifier_model.append_child_item(None, ui.SimpleStringModel(session))
        self._session_changed_fn_id = self.session_identifier_model.add_item_changed_fn(self.on_session_identifier_changed)
        #if self._session_identifiers:
            #self.session_identifier_model.set_value(self._session_identifiers[0])
        end_time = time.perf_counter()
        print(f"on_folder_number_changed execution time: {end_time - start_time} seconds")
        return "on_folder_number_changed success"
    
    def get_session_identifiers(self, folder_number):
        print("getting session identifiers")
        start_time = time.perf_counter()
        base_path = "Z:/nuscenes"
        # Get list of session identifiers
        cam_sweep_path = os.path.join(base_path, f'v1.0-trainval{folder_number} blobs/sweeps/CAM_FRONT/')
        lidar_sweep_path = os.path.join(base_path, f'v1.0-trainval{folder_number} blobs/sweeps/LIDAR_TOP/')
        cam_files = glob.glob(os.path.join(cam_sweep_path, '*.jpg'))
        lidar_files = glob.glob(os.path.join(lidar_sweep_path, '*.pcd.usd'))
        print("found", len(cam_files), "cam files and", len(lidar_files), "lidar files")
        cam_sessions = set(os.path.basename(f).split('__')[0] for f in cam_files)
        lidar_sessions = set(os.path.basename(f).split('__')[0] for f in lidar_files)
        sessions = sorted(cam_sessions.intersection(lidar_sessions))
        print("sessions:", sessions)
        #logging.info(f"Session identifiers for folder {folder_number}: {sessions}")
        end_time = time.perf_counter()
        print(f"get_session_identifiers execution time: {end_time - start_time} seconds")
        return sessions

    def on_session_identifier_changed(self, model, *args):
        start_time = time.perf_counter()

        session_identifier = model.get_item_value_model().as_int
        self._current_session_identifier = self._session_identifiers[session_identifier] #str(model.get_item_children()[session_identifier])
        print("session identifier changed")
        print("session id:", self._current_session_identifier)

        # Load image and LiDAR data
        self.load_image_data()
        self.load_lidar_data()
        #print("loaded lidar data", self._lidar_timestamps)
        # Update the slider range
        self._image_timestamps = self.get_timestamps("{0:0=2d}".format(self.folder_number_model.get_item_value_model().as_int), self._current_session_identifier)
        self._global_sampled_image_timestamps = self.sample_timestamps(self._image_timestamps)
        self._global_sampled_lidar_timestamps = [self._lidar_timestamps[self.find_closest_index(self._lidar_timestamps, idx)] for idx in self._global_sampled_image_timestamps]

        print("global sampled image timestamps:", self._global_sampled_image_timestamps)
        print("global sampled lidar timestamps:", self._global_sampled_lidar_timestamps)
        
        #TODO: Insert code to pre-load sampled timestamps from datalake

        if self._image_timestamps:
            min_timestamp = min(self._image_timestamps)
            max_timestamp = max(self._image_timestamps)
            print(f"Timestamp range: {min_timestamp} - {max_timestamp}")
            self.timestamp_model.set_max(max_timestamp)
            self.timestamp_model.set_min(min_timestamp)
            self.timestamp_slider.max = max_timestamp
            self.timestamp_slider.min = min_timestamp
            print("Current model range:", self.timestamp_model.min, "to", self.timestamp_model.max)
            print("Current slider range:", self.timestamp_slider.min, "to", self.timestamp_slider.max)
            self.timestamp_model.set_value(min_timestamp)
            self.on_timestamp_changed(self.timestamp_model)

        end_time = time.perf_counter()
        print(f"on_session_identifier_changed execution time: {end_time - start_time} seconds")
        return "on_session_identifier_changed success"
    
    def get_timestamps(self, folder_number, session_identifier):
        start_time = time.perf_counter()

        # Get list of camera timestamps
        print("getting timestamps")
        base_path = "Z:/nuscenes"
        cam_sweep_path = os.path.join(base_path, f'v1.0-trainval{folder_number} blobs/sweeps/CAM_FRONT/')
        print("getting cam files from:", cam_sweep_path)
        print("glob:", os.path.join(cam_sweep_path, f'{session_identifier}__CAM_FRONT__*.jpg'))
        cam_files = glob.glob(os.path.join(cam_sweep_path, f'{session_identifier}__CAM_FRONT__*.jpg'))
        print("cam files:", cam_files)
        cam_timestamps = [int(os.path.basename(f).split('__')[2].split('.')[0]) for f in cam_files]
        timestamps = sorted(cam_timestamps)
        print("timestamps:", timestamps)
        end_time = time.perf_counter()
        print(f"get_timestamps execution time: {end_time - start_time} seconds")
        return timestamps


    def load_image_data(self):
        start_time = time.perf_counter()

        print("loading image timestamps")
        folder_path = os.path.join(self._base_path, f"v1.0-trainval{self._current_folder_number} blobs", "sweeps", "CAM_FRONT")
        pattern = os.path.join(folder_path, f"{self._current_session_identifier}__CAM_FRONT__*.jpg")
        self._image_files = sorted(glob.glob(pattern))
        self._image_timestamps = []
        for file in self._image_files:
            filename = os.path.basename(file)
            timestamp = int(filename.split("__")[2].split(".")[0])
            self._image_timestamps.append(timestamp)

        end_time = time.perf_counter()
        print(f"load_image_data execution time: {end_time - start_time} seconds")

    def load_lidar_data(self):
        start_time = time.perf_counter()
        print("loading lidar timestamps")
        folder_path = os.path.join(self._base_path, f"v1.0-trainval{self._current_folder_number} blobs", "sweeps", "LIDAR_TOP")
        pattern = os.path.join(folder_path, f"{self._current_session_identifier}__LIDAR_TOP__*.pcd.usd")
        self._lidar_files = sorted(glob.glob(pattern))
        self._lidar_timestamps = []
        for file in self._lidar_files:
            filename = os.path.basename(file)
            timestamp = int(filename.split("__")[2].split(".")[0])
            self._lidar_timestamps.append(timestamp)

        end_time = time.perf_counter()
        print(f"load_lidar_data execution time: {end_time - start_time} seconds")

    def on_timestamp_changed(self, model=None):
        start_time = time.perf_counter()

        print("timestamp changed")
        if model == None:
            model = self.timestamp_model
        index = model.get_value_as_int()
        # Display the image and pointcloud at the selected index
        self.display_image(index)
        self.display_pointcloud(index)

        fifty_before_image_timestamps, fifty_after_image_timestamps = self.get_neighbors(self._image_timestamps, index)
        fifty_before_lidar_timestamps, fifty_after_lidar_timestamps = self.get_neighbors(self._lidar_timestamps, index)

        #TODO: Insert code to pre-load surrounding 100 (50 before & 50 after) timestamps from datalake

        end_time = time.perf_counter()
        print(f"on_timestamp_changed execution time: {end_time - start_time} seconds")

    def drag_slider(self, model=None):
        print("dragging slider")
        if model == None:
            model = self.timestamp_model
        index = model.get_value_as_int()
        # Display globally sampled timestamps while dragging
        self.display_image(self._global_sampled_image_timestamps[self.find_closest_index(self._global_sampled_image_timestamps, index)])
        self.display_pointcloud(self._global_sampled_lidar_timestamps[self.find_closest_index(self._global_sampled_lidar_timestamps, index)])

    def display_image(self, index):
        start_time = time.perf_counter()

        print('checking if image should be updated')
        real_idx = self.find_closest_index(self._image_timestamps, index)#self._image_timestamps.index(index)
        print("current image", self._current_image, ("!=" if self._current_image != real_idx else "=="), real_idx, ", proceeding")
        if real_idx != self._current_image:
            print("proceeding to display image")
            self._current_image = real_idx
            if 0 <= real_idx < len(self._image_files):
                image_file = self._image_files[real_idx]
                self.image_widget.source_url = f"file://{image_file}"
            else:
                self.image_widget.source_url = ""

        end_time = time.perf_counter()
        print(f"display_image execution time: {end_time - start_time} seconds")

    def display_pointcloud(self, index):
        start_time = time.perf_counter()

        print('checking if lidar should be updated')
        # Find the timestamp of the selected image
        image_timestamp = index#self._image_timestamps[index]
        # Find the closest LiDAR timestamp
        lidar_idx = self.find_closest_index(self._lidar_timestamps, image_timestamp)
        print("current lidar", self._current_lidar, ("!=" if self._current_lidar != lidar_idx else "=="), lidar_idx, ", proceeding")
        if lidar_idx != self._current_lidar:
            print("proceeding to display lidar")
            self._current_lidar = lidar_idx
            if lidar_idx is not None:
                lidar_file = self._lidar_files[lidar_idx]
                print("loading .usd from", lidar_file)
                # Load the USD file into the stage
                stage = omni.usd.get_context().get_stage()
                if stage is None:
                    print("No active stage found.")
                    return
                # Remove existing pointcloud prim if any
                pointcloud_prim_path = Sdf.Path("/World/LiDARPointCloud")
                if pointcloud_prim_path and stage.GetPrimAtPath(pointcloud_prim_path):
                    # Remove the existing prim
                    omni.kit.commands.execute('DeletePrims', paths=[str(pointcloud_prim_path)])
                # Reference the pointcloud USD file
                pointcloud_prim = stage.DefinePrim(pointcloud_prim_path, "Points")
                print("Defined prim", pointcloud_prim)
                pointcloud_prim.GetReferences().AddReference(assetPath=lidar_file, primPath="/Root/PointCloud")
                # Focus the camera on the point cloud
                #self.focus_on_prim(pointcloud_prim_path)
            else:
                # Clear the pointcloud display
                stage = omni.usd.get_context().get_stage()
                pointcloud_prim_path = Sdf.Path("/World/LiDARPointCloud")
                if stage.GetPrimAtPath(pointcloud_prim_path):
                    omni.kit.commands.execute('DeletePrims', paths=[str(pointcloud_prim_path)])

        end_time = time.perf_counter()
        print(f"display_pointcloud execution time: {end_time - start_time} seconds")

    """def focus_on_prim(self, prim_path):
        # Get the stage and the prim
        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if prim:
            # Select the prim
            selection = omni.usd.get_context().get_selection()
            selection.set_selected_prim_paths([str(prim_path)], False)
            # Get the active viewport
            viewport_interface = omni.kit.viewport.get_viewport_interface()
            if viewport_interface is not None:
                viewport_window = viewport_interface.get_viewport_window()
                if viewport_window:
                    # Focus on the selected prim
                    viewport_window.focus_on_selected()
        else:
            print(f"Prim {prim_path} not found.")"""

    def find_closest_index(self, timestamps, target):
        start_time = time.perf_counter()

        print("finding closest available index to", target)
        if not timestamps:
            return None
        idx = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - target))
        end_time = time.perf_counter()
        print(f"find_closest_index execution time: {end_time - start_time} seconds")
        return idx

    def sample_timestamps(self, lst, num_samples=100):
        start_time = time.perf_counter()

        print("sampling",num_samples, "global timestamps")
        L = len(lst)
        if L <= num_samples:
            end_time = time.perf_counter()
            print(f"sample_timestamps execution time: {end_time - start_time} seconds")
            return lst
        else:
            indices = np.linspace(0, L - 1, num=num_samples, dtype=int)
            sampled_list = [lst[idx] for idx in indices]
            end_time = time.perf_counter()
            print(f"sample_timestamps execution time: {end_time - start_time} seconds")
            return sampled_list



    def get_neighbors(self, timestamps, x, n=50):
        start_time = time.perf_counter()
        print("getting", n*2, "local timestamps")
        index = bisect.bisect_left(timestamps, x)
        
        start_before = max(0, index - n)
        timestamps_before = timestamps[start_before:index]
        
        end_after = index + n + 1
        timestamps_after = timestamps[index + 1:end_after]

        end_time = time.perf_counter()
        print(f"get_neighbors execution time: {end_time - start_time} seconds")
        
        return timestamps_before, timestamps_after


