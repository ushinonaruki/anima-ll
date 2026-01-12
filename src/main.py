import requests
from brain import think, vital
from common import config
from dtos.packet import AnimaLlPacket
from sensory.body import system
from sensory.directive import terminal
from sensory.site import jma


def main():
    print(config.UI_BOOT)
    vital.execute()

    while True:
        try:
            cmd_dto = terminal.execute()
            jma_dto = jma.execute()
            sys_dto = system.execute()
            packet = AnimaLlPacket(cmd=cmd_dto, jma=jma_dto, sys=sys_dto)

            response = think.execute(packet.serialize())
            print(f"{config.UI_ANIMA_LABEL}{response}")

        except requests.exceptions.ConnectionError:
            print(config.UI_ERR_CONN)
            break
        except KeyboardInterrupt:
            print(config.UI_ERR_INTERRUPT)
            break
        except EOFError:
            print(config.UI_ERR_EOF)
            break
        except Exception as e:
            print(config.UI_ERR_GENERIC.format(error=e))
            break


if __name__ == "__main__":
    main()
