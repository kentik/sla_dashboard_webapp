from dataclasses import dataclass

MatrixCellColor = str  # format: "rgb(255,0,0)" for red color


@dataclass(frozen=True)
class Matrix:
    cell_color_healthy: MatrixCellColor
    cell_color_warning: MatrixCellColor
    cell_color_critical: MatrixCellColor
    cell_color_nodata: MatrixCellColor
