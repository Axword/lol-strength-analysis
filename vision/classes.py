"""
Class IDs for Touch / structure object detection (must match dataset.yaml).
"""

CLASSES = [
    "voidmite",  # Hunger Voidmite attacking a structure
    "turret",
    "inhibitor",
    "nexus",
    "champion",  # any champ model (team via color later)
    "replay_bumper",  # EWC REPLAY full-screen card — skip for Touch
    "touch_burn_fx",  # purple Touch DoT VFX on structure (if visible)
    "grub_buff_icon",  # HUD / over-champ Touch of the Void icon
    "baron_buff_icon",
]

CLASS_TO_ID = {n: i for i, n in enumerate(CLASSES)}
ID_TO_CLASS = {i: n for i, n in enumerate(CLASSES)}

# Label Studio rectangle labeling config (paste into project)
LABEL_STUDIO_XML = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="voidmite" background="#9b59b6"/>
    <Label value="turret" background="#e67e22"/>
    <Label value="inhibitor" background="#e74c3c"/>
    <Label value="nexus" background="#c0392b"/>
    <Label value="champion" background="#3498db"/>
    <Label value="replay_bumper" background="#95a5a6"/>
    <Label value="touch_burn_fx" background="#8e44ad"/>
    <Label value="grub_buff_icon" background="#1abc9c"/>
    <Label value="baron_buff_icon" background="#f1c40f"/>
  </RectangleLabels>
</View>
"""
