from ..filepath import BIDSFilePath


def is_sidecar_pair(one: BIDSFilePath, two: BIDSFilePath) -> bool:
    return (
        one.relpath.parent == two.relpath.parent
        and one.stem == two.stem
        and (
            (one.is_metadata() and not two.is_metadata())
            or (two.is_metadata() and not one.is_metadata())
        )
        and one.extension != two.extension
    )
