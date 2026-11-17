import argparse
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import traceback
from types import ModuleType
from unittest.mock import patch


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


class ResultRef:
    def __init__(self, value=None, operation=None):
        self.value = value
        self.operation = operation
        self.ready = operation is None

    def resolve(self):
        if not self.ready:
            self.value = self.operation()
            self.ready = True
        return self.value


class LocalRay(ModuleType):
    def __init__(self):
        super().__init__("ray")
        self.calls = []
        self.waits = []

    def remote(self, target):
        runtime = self
        if isinstance(target, type):
            class Actor:
                cls = target

                def remote(self, *args, **kwargs):
                    instance = target(*args, **kwargs)

                    class Handle:
                        def __getattr__(self, name):
                            class Method:
                                def remote(self, *args, **kwargs):
                                    return ResultRef(operation=lambda: getattr(instance, name)(*args, **kwargs))
                            return Method()

                    return Handle()

            return Actor()

        class Task:
            def remote(self, *args, **kwargs):
                runtime.calls.append((args, kwargs))
                return ResultRef(target(*args, **kwargs))

        return Task()

    def get(self, refs):
        self.waits.append(len(self.calls))
        if isinstance(refs, list):
            return [self.get_value(ref) for ref in refs]
        return self.get_value(refs)

    def get_value(self, ref):
        expect(isinstance(ref, ResultRef), "ray.get must receive task or actor references")
        return ref.resolve()


@contextmanager
def fixture_module():
    runtime = LocalRay()
    path = Path(__file__).with_name("ray_images.py")
    spec = importlib.util.spec_from_file_location("_unit_ray_images", path)
    student = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"ray": runtime}):
        spec.loader.exec_module(student)
        yield student, runtime


def images():
    import numpy as np
    return [np.arange(18, dtype=np.uint8).reshape(2, 3, 3),
            np.full((1, 4, 3), 255, dtype=np.uint8)]


def same_images(actual, expected):
    import numpy as np
    expect(isinstance(actual, list) and len(actual) == len(expected), "return one image per input in a list")
    for result, want in zip(actual, expected):
        expect(isinstance(result, np.ndarray), "return image arrays")
        np.testing.assert_array_equal(result, want)


def unit_task():
    import numpy as np
    with fixture_module() as (student, runtime):
        expect(callable(getattr(student.process_image_task, "remote", None)), "keep @ray.remote on process_image_task")
        for image in images():
            original = image.copy()
            expected = np.full_like(image, 17)
            with patch.object(student, "process_image", return_value=expected) as process:
                result = runtime.get(student.process_image_task.remote(image))
                expect(process.call_count == 1 and process.call_args.args[0] is image,
                       "call the supplied process_image once with this image")
                np.testing.assert_array_equal(result, expected)
            np.testing.assert_array_equal(image, original)


def unit_parallel():
    import numpy as np
    with fixture_module() as (student, runtime):
        task = runtime.remote(lambda image: 255 - image)
        with patch.object(student, "process_image_task", task):
            source = images()
            for batch in ([source[1], source[0], source[1]], []):
                original = [image.copy() for image in batch]
                original_ids = [id(image) for image in batch]
                runtime.calls.clear()
                runtime.waits.clear()
                result = student.process_parallel(batch)
                expect([id(args[0]) for args, kwargs in runtime.calls] == original_ids,
                       "submit one task for each image, including duplicates, in input order")
                expect(runtime.waits == [len(batch)] or (not batch and not runtime.waits),
                       "submit all tasks before gathering once")
                same_images(result, [255 - image for image in original])
                expect([id(image) for image in batch] == original_ids, "keep the input list unchanged")
                for image, before in zip(batch, original):
                    np.testing.assert_array_equal(image, before)


def unit_add():
    with fixture_module() as (student, runtime):
        actor = student.PixelCounter
        expect(hasattr(actor, "cls"), "keep @ray.remote on PixelCounter")
        counter = actor.cls()
        other = actor.cls()
        expect(counter.total == 0, "start each counter at zero")
        counter.total = 11
        for value in (6, 0, 2):
            counter.add(value)
        expect(counter.total == 19, "add each count to the existing total")
        expect(other.total == 0, "each actor must own a separate total")


def unit_get_total():
    with fixture_module() as (student, runtime):
        actor = student.PixelCounter
        expect(hasattr(actor, "cls"), "keep @ray.remote on PixelCounter")
        counter = actor.cls()
        for total in (0, 137, 4):
            counter.total = total
            expect(counter.get_total() == total, "return the actor's current total")
            expect(counter.total == total, "reading the total must not change it")


def unit_counted_task():
    import numpy as np
    with fixture_module() as (student, runtime):
        expect(callable(getattr(student.process_and_count, "remote", None)), "keep @ray.remote on process_and_count")
        updates = []

        class Counter:
            def add(self, count):
                updates.append(count)

        counter = runtime.remote(Counter).remote()
        for image in images():
            original = image.copy()
            expected = np.full_like(image, 29)
            updates.clear()
            with patch.object(student, "process_image", return_value=expected) as process:
                result_ref = student.process_and_count.remote(image, counter)
                expect(updates == [image.shape[0] * image.shape[1]],
                       "wait for one actor update before returning; count pixels, not RGB channel values")
                expect(process.call_count == 1 and process.call_args.args[0] is image,
                       "call the supplied process_image once with this image")
                np.testing.assert_array_equal(runtime.get(result_ref), expected)
            np.testing.assert_array_equal(image, original)


def unit_row():
    import numpy as np
    with fixture_module() as (student, runtime):
        expect(callable(student.process_row) and not hasattr(student.process_row, "remote"),
               "process_row must be a plain function for Dataset.map")
        for image in images():
            original = image.copy()
            row = {"id": 7, "source": "tiny-fixture", "image": image}
            expected = np.full_like(image, 43)
            with patch.object(student, "process_image", return_value=expected) as process:
                result = student.process_row(row)
                expect(isinstance(result, dict) and result is not row, "return a copied row")
                expect(set(result) == set(row) and result["id"] == 7 and result["source"] == "tiny-fixture",
                       "preserve every other field")
                expect(process.call_count == 1 and process.call_args.args[0] is image,
                       "call the supplied process_image with the row's image")
                np.testing.assert_array_equal(result["image"], expected)
            expect(row["image"] is image and set(row) == {"id", "source", "image"}, "keep the input row unchanged")
            np.testing.assert_array_equal(image, original)


def integration():
    import numpy as np
    import ray
    import ray.data
    import ray_images as student

    ray.init(num_cpus=2, include_dashboard=False, log_to_driver=False)
    try:
        batch = [np.full((2, 3, 3), value, dtype=np.uint8) for value in (0, 127, 255)]
        original = [image.copy() for image in batch]
        expected = [255 - image for image in original]
        same_images(student.process_parallel(batch), expected)
        counter = student.PixelCounter.remote()
        refs = [student.process_and_count.remote(image, counter) for image in batch]
        same_images(ray.get(refs), expected)
        expect(ray.get(counter.get_total.remote()) == 18, "three 2-by-3 RGB images contain 18 pixels")
        rows = [{"id": i, "source": "integration", "image": image} for i, image in enumerate(batch)]
        result = ray.data.from_items(rows).map(student.process_row).take_all()
        result.sort(key=lambda row: row["id"])
        expect([row["id"] for row in result] == [0, 1, 2], "Ray Data must preserve all row IDs")
        expect(all(row["source"] == "integration" for row in result), "Ray Data must preserve metadata")
        same_images([row["image"] for row in result], expected)
        same_images(batch, original)
    finally:
        ray.shutdown()


UNIT_TESTS = {
    "process_image_task": unit_task,
    "process_parallel": unit_parallel,
    "PixelCounter.add": unit_add,
    "PixelCounter.get_total": unit_get_total,
    "process_and_count": unit_counted_task,
    "process_row": unit_row,
}
ALL_TESTS = {**UNIT_TESTS, "Ray integration": integration}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab 11 image-processing correctness checks.")
    parser.add_argument("--list", action="store_true", help="list the six function targets")
    parser.add_argument("--unit", nargs="?", const="all", choices=["all", *UNIT_TESTS], metavar="TARGET",
                        help="test one function or all functions with local Ray stand-ins")
    parser.add_argument("-v", action="store_true", help="show failure tracebacks")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(UNIT_TESTS))
        return 0
    selected = UNIT_TESTS if args.unit == "all" else {args.unit: UNIT_TESTS[args.unit]} if args.unit else ALL_TESTS
    try:
        import numpy
        if not args.unit:
            import ray
            import ray.data
    except ImportError as error:
        for name in selected:
            print(f"[FAIL] {name}: required dependency missing: {error}")
        print("Install dependencies: python3 -m pip install -r requirements-ray.txt")
        print(f"0/{len(selected)} checks passed")
        return 1
    passed = 0
    for name, check in selected.items():
        try:
            check()
            passed += 1
            print(f"[PASS] {name}")
        except Exception as error:
            detail = "not implemented yet" if isinstance(error, NotImplementedError) else f"{type(error).__name__}: {error}"
            print(f"[FAIL] {name}: {detail}")
            if args.v:
                traceback.print_exc()
    print(f"{passed}/{len(selected)} checks passed")
    return 0 if passed == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
