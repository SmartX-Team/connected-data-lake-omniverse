'''An Omniverse Kit Extension module for nuScenes Visualization
'''
import asyncio
from logging import info, warning

from typing_extensions import final, override
from pxr import Sdf, Gf, Usd
#from usdrt import Sdf, Gf, Usd
import numpy as np 
from concurrent.futures import ThreadPoolExecutor


import omni.ext  # pylint: disable=import-error
import omni.kit.commands  # pylint: disable=import-error
import omni.kit.viewport  # pylint: disable=import-error
import omni.ui as ui  # pylint: disable=import-error
import omni.usd  # pylint: disable=import-error

try:
    from .utils.deps import install_dependencies
    install_dependencies()
except ImportError as e:
    raise e

from cdlake import Cdl  # pylint: disable=import-error	

from .dataloader import BaseDataLoader, Category, load_dataset

__all__ = [
    'RGBLiDARVisualizerExtension',
]


class RGBLiDARVisualizerExtension(omni.ext.IExt):
    '''An Omniverse Kit Extension for nuScenes Visualization'''

    # UI
    _ui_cameras: dict[str, ui.Image] = {}
    _ui_cameras_keys = [
        'cam_front',
    ]
    _ui_dataset: ui.StringField
    _ui_dataset_catalog: ui.ComboBox
    _ui_scene_selector: ui.ComboBox
    _ui_timestamp_slider: ui.IntSlider
    _ui_dataset_status: ui.Label

    # Windows
    _window_cameras: dict[str, ui.Window] = {}
    _window_control_panel: ui.Window | None

    # States
    _cache_dir: str = './cache'	
    _cdl: Cdl	
    _data_category: Category = 'samples'
    _data_loader: BaseDataLoader | None = None
    _data_loader_url: str = ''
    _dataset_catalog_index_local: int = 0	
    _dataset_catalog_index_custom: int = 1	
    _datasets: list[str] = []

    @final
    @override
    def on_startup(self, _ext_id: str) -> None:
        '''Initialize the extension'''
        info('[RGBLiDARVisualizer] Extension started')
        print(omni.kit.commands.get_commands_list())

        # Define Connected Data Lake	
        self._cdl = Cdl()

        # Define camera windows
        for name in self._ui_cameras_keys:
            self._create_camera_window(name)

        # Define control panel
        self._window_control_panel = ui.Window(
            title='nuScenes RGB & LiDAR Visualizer',
            width=400,
            height=600,
        )
        with self._window_control_panel.frame:
            with ui.VStack():
                ui.Label('Select Dataset:')
                self._ui_dataset_catalog = ui.ComboBox()
                self._ui_dataset = ui.StringField(
                    model=ui.SimpleStringModel('./data/nuscenes'),
                    height=25,
                    visible=False,
                )
                self._ui_dataset_status = ui.Label(
                    'Loading...',
                    height=40,
                )

                ui.Label('Select Scene:')
                self._ui_scene_selector = ui.ComboBox()

                ui.Label('Select Timestamp:')
                self._ui_timestamp_slider = ui.IntSlider(
                    model=ui.SimpleIntModel(),
                )
                
                self._loop_running = False

                self.play_button = ui.Button("Play", clicked_fn=lambda: asyncio.ensure_future(clicked()))

                async def clicked():
                    if self._loop_running:
                        self._loop_running = False
                        self.play_button.text = "Play"
                    else:
                        self._loop_running = True
                        self.play_button.text = "Stop"

                        if self._data_loader is not None:
                            for x in self._data_loader.timestamps:
                                if x % 500000 == 0:
                                    if not self._loop_running:
                                        break
                                    self._ui_timestamp_slider.model.set_value(x)
                                    #self._reload_screen()
                                    self._on_timestamp_changed(self._ui_timestamp_slider.model)
                                    await asyncio.sleep(0.5)
                            self._loop_running = False
                            self.play_button.text = "Play"


                # Instructions
                ui.Label(
                    'LiDAR Pointcloud is displayed in the main viewport.',
                    height=40,
                )

                # Register callbacks
                self._ui_dataset_catalog.model.add_item_changed_fn(	
                    self._on_dataset_catalog_changed,	
                )
                self._ui_dataset.model.add_end_edit_fn(
                    self._on_dataset_changed,
                )
                self._ui_scene_selector.model.add_item_changed_fn(
                    self._on_scene_changed,
                )
                self._ui_timestamp_slider.model.add_end_edit_fn(
                    self._on_timestamp_changed,
                )
                self._ui_timestamp_slider.model.add_value_changed_fn(
                    self._on_timestamp_lookup,
                )

                # Fetch dataset
                self._reload_dataset_catalog()
    @ final
    @ override
    def on_shutdown(self) -> None:
        '''Finalize the extension'''
        info('[RGBLiDARVisualizer] Extension shutdown')
        self._ui_cameras = {}
        self._window_cameras = {}
        self._window_control_panel = None
        self._data_loader = None

    def _create_camera_window(
        self,
        name: str,
    ):
        # Define window
        window = ui.Window(
            title=f'nuScenes RGB Visualizer - {name}',
            width=400,
            height=400,
        )
        self._window_cameras[name] = window

        # Display image
        with window.frame:
            image = ui.Image('')
        self._ui_cameras[name] = image

    def _reload_dataset_catalog(self) -> None:	
        # Reload catalog	
        self._datasets = ['dataset-b', 'dataset-a']	

        # Reload catalog UI	
        for dataset in self._ui_dataset_catalog.model.get_item_children():	
            self._ui_dataset_catalog.model.remove_item(dataset)	
        if self._data_loader is not None:	
            for dataset in self._datasets:	
                self._ui_dataset_catalog.model.append_child_item(	
                    None,	
                    ui.SimpleStringModel(dataset),	
                )	

            self._dataset_catalog_index_local = len(self._datasets)	
            self._ui_dataset_catalog.model.append_child_item(	
                None,	
                ui.SimpleStringModel('Local Filesystem'),	
            )	
            self._dataset_catalog_index_custom = len(self._datasets) + 1	
            self._ui_dataset_catalog.model.append_child_item(	
                None,	
                ui.SimpleStringModel('Custom'),	
            )	

        # Reload dataset	
        return self._reload_dataset()

    def _reload_dataset(self) -> None:
        return self._on_dataset_changed(self._ui_dataset.model)

    def _reload_scenes(self) -> None:
        # Reload scenes
        for scene in self._ui_scene_selector.model.get_item_children():
            self._ui_scene_selector.model.remove_item(scene)
        if self._data_loader is not None:
            for scene in self._data_loader.scenes:
                self._ui_scene_selector.model.append_child_item(
                    None,
                    ui.SimpleStringModel(scene),
                )

        # Reload timestamps
        return self._reload_timestamps()

    def _reload_timestamps(self) -> None:
        if self._data_loader is not None:
            timestamps = self._data_loader.timestamps
            self._ui_timestamp_slider.min = timestamps.start
            self._ui_timestamp_slider.max = timestamps.stop
            self._ui_timestamp_slider.model.set_min(timestamps.start)
            self._ui_timestamp_slider.model.set_max(timestamps.stop)
            self._ui_timestamp_slider.model.set_value(
                self._data_loader.timestamp,
            )
            # Sample global timestamps for caching
            self._global_sampled_ts = self.sample_timestamps(timestamps, num_samples=100)

            # Run caching asynchronously
            asyncio.run(self.cache_timestamps_async(self._global_sampled_ts))

        # Reload the screen
        return self._reload_screen()

    def _reload_screen(
        self,
        lookup_timestamp: int | None = None,
    ) -> None:
        # Display the image and pointcloud at the selected timestamp
        if self._data_loader is not None:
            if lookup_timestamp is None:
                for name, ui_image in self._ui_cameras.items():
                    ui_image.source_url = getattr(self._data_loader, name)
                self._display_pointcloud(self._data_loader.lidar_top)
            else:
                # Lookup only 1 image
                name = self._ui_cameras_keys[0]
                ui_image = self._ui_cameras[name]
                ui_image.source_url = getattr(self._data_loader, f'lookup_{name}')(  # noqa: E501
                    timestamp=lookup_timestamp,
                )

    def _on_dataset_catalog_changed(self, model, *_args) -> None:	
        # # Propagate value to the DataLoader	
        index = model.get_item_value_model().as_int	
        if self._data_loader is None:	
            return  # nothing changed	

        if index < len(self._datasets):	
            url = f's3://{self._datasets[index]}'	
        elif index == self._dataset_catalog_index_local:	
            url = './data/nuscenes'	
        else:	
            self._ui_dataset.visible = True	
            return	

        self._ui_dataset.visible = False	
        self._ui_dataset.model.set_value(url)	
        return self._reload_dataset()

    def _on_dataset_changed(self, model) -> None:
        url = model.as_string
        if self._data_loader_url == url:
            return
        self._data_loader_url = url

        # Reload data loader
        has_old_data_loader = self._data_loader is not None	
        try:
            self._ui_dataset_status.text = 'Loading...'
            self._data_loader = load_dataset(
                category=self._data_category,
                url=self._data_loader_url
            )
            self._ui_dataset_status.text = f'Ok({self._data_loader!r})'
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._ui_dataset_status.text = repr(e)
            raise e
        finally:
            if self._data_loader is not None:
                self._data_loader.checkout_dataset()

            # Reset all values
            if not has_old_data_loader:	
                self._reload_dataset_catalog()
            self._reload_scenes()

    def _on_scene_changed(self, model, *_args) -> None:
        # Propagate value to the DataLoader
        index = model.get_item_value_model().as_int
        if self._data_loader is None \
                or not self._data_loader.checkout_scene(index):
            return  # nothing changed

        # Reload timestamps
        return self._reload_timestamps()

    def _on_timestamp_changed(self, model) -> None:
        # Propagate value to the DataLoader
        timestamp = model.get_value_as_int()
        if self._data_loader is None \
                or not self._data_loader.seek(timestamp):
            return  # nothing changed

        # Reload the screen
        return self._reload_screen()

    def _on_timestamp_lookup(self, model) -> None:
        timestamp = model.get_value_as_int()
        return self._reload_screen(
            lookup_timestamp=timestamp,
        )

    def _display_pointcloud(self, url: str) -> None:
        # Load the USD file into the stage
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            #warning('No active stage found.')
            stage: Usd.Stage = Usd.Stage.CreateInMemory()
            #return

        # Remove existing pointcloud prim if any
        # pylint: disable=no-member
        pointcloud_prim_path = Sdf.Path('/World/LiDARPointCloud')
        pointcloud_prim = stage.GetPrimAtPath(pointcloud_prim_path)
        """if pointcloud_prim.IsValid():
            stage.RemovePrim(pointcloud_prim_path)"""

        # Reference the pointcloud USD file
        if not pointcloud_prim.IsValid():
            pointcloud_prim = stage.DefinePrim(pointcloud_prim_path, 'Points')
        pointcloud_prim.GetReferences().ClearReferences()
        pointcloud_prim.GetReferences().AddReference(
            assetPath=url,
            primPath='/Root/PointCloud',
        )

        if not pointcloud_prim.GetAttribute('xformOp:rotateXYZ'):
            omni.kit.commands.execute('CreateDefaultXformOnPrimCommand',
                prim_path=Sdf.Path('/World/LiDARPointCloud'),
                stage=stage)
        omni.kit.commands.execute('ChangePropertyCommand',
            prop_path=Sdf.Path('/World/LiDARPointCloud.xformOp:rotateXYZ'),
            value=Gf.Vec3f(-90, 0, 0),
            prev=Gf.Vec3f(0, 0, 0))
         

        # Focus the camera on the point cloud
        # self.focus_on_prim(pointcloud_prim_path)

    async def cache_timestamp(self, timestamp, executor):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, self._data_loader.lookup_lidar_top, timestamp)

    async def cache_timestamps_async(self, timestamps):
        executor = ThreadPoolExecutor()
        tasks = [self.cache_timestamp(ts, executor) for ts in timestamps]
        await asyncio.gather(*tasks)
        executor.shutdown(wait=True)

    def sample_timestamps(self, lst, num_samples=100):
        L = len(lst)
        if L <= num_samples:
            return lst
        else:
            indices = np.linspace(0, L - 1, num=num_samples, dtype=int)
            sampled_list = [lst[idx] for idx in indices]
            return sampled_list
