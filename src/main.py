import os
from brain import think, vital
from dtos.packet import AnimaLlPacket
from effector.voice import voice
from requests.exceptions import ConnectionError
from sensory.body import system
from sensory.directive import terminal
from sensory.site import jma

OUTPUT_LABEL: str = os.environ.get("OUTPUT_LABEL")


def main():
    vital.execute()

    while True:
        try:
            cmd_dto = terminal.execute()
            packet = AnimaLlPacket(cmd=cmd_dto)
            # jma_dto = jma.execute()
            # sys_dto = system.execute()
            # packet = AnimaLlPacket(cmd=cmd_dto, jma=jma_dto, sys=sys_dto)

            response = think.execute(packet.serialize())
            voice.execute(response)
            print(f"{OUTPUT_LABEL}{response}")

        except ConnectionError as e:
            print(f"ConnectionError: {e}")
            break
        except KeyboardInterrupt as e:
            print(f"KeyboardInterrupt: {e}")
            break
        except EOFError as e:
            print(f"EOFError: {e}")
            break
        except Exception as e:
            print(f"Exception: {e}")
            break


if __name__ == "__main__":
    main()
