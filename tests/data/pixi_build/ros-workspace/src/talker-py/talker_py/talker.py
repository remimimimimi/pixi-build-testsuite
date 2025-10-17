import sys
import argparse
from typing import Any

import rclpy  # type: ignore[import-not-found]
from geometry_msgs.msg import Point  # type: ignore[import-not-found]
from rclpy.node import Node  # type: ignore[import-not-found]


class CoordinatePublisher(Node):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(node_name="coordinate_publisher")
        self.publisher_ = self.create_publisher(Point, "coordinates", 10)

    def publish_coordinates(self, x: float, y: float) -> None:
        msg = Point()
        msg.x = x
        msg.y = y
        msg.z = 0.0  # Assuming z is not used, set to 0
        self.publisher_.publish(msg)
        self.get_logger().info(f"Publishing: x={x}, y={y}")


def main(args: Any = None) -> None:
    rclpy.init(args=args)
    node = CoordinatePublisher()

    parser = argparse.ArgumentParser(description="Send coordinates over a ROS2 topic")
    parser.add_argument("x", type=float, help="X coordinate")
    parser.add_argument("y", type=float, help="Y coordinate")

    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])

    try:
        node.publish_coordinates(args.x, args.y)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    print("HALLO OUWE")
    main()
