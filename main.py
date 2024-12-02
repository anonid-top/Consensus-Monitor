import asyncio
import signal
from platform import system
from aiohttp import ClientSession
from utils.args import args
from src.dashboard import ConsensusDashboard
from utils.logger import logger

async def run_dashboard(dashboard: ConsensusDashboard):
    """
    Run the ConsensusDashboard and handle graceful shutdown on signals.
    """
    try:
        await dashboard.start()
    except Exception as e:
        logger.error(f"Unhandled exception in the dashboard: {e}", exc_info=True)
    finally:
        logger.info("Dashboard stopped cleanly.")


async def main():
    """
    Main function to set up the dashboard and handle signals for graceful shutdown.
    """
    logger.info("Starting Dashboard...")

    async with ClientSession() as session:
        dashboard = ConsensusDashboard(
            rpc=args.rpc,
            refresh_per_second=args.refresh_per_second,
            disable_emojis=args.disable_emojis,
            refresh_validators=args.refresh_validators,
            refresh_consensus_state=args.refresh_consensus_state,
            refresh_upgrade_plan=args.refresh_upgrade_plan,
            refresh_node=args.refresh_node,
            refresh_block_time=args.refresh_block_time,
            user_tz=args.tz,
            block_time_number=args.block_time_number,
            columns=args.columns,
            hashes=args.hashes,
            session=session,
        )

        def shutdown_handler():
            logger.info("Shutdown signal received. Stopping Dashboard...")
            for task in asyncio.all_tasks():
                task.cancel()

        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown_handler)
            except NotImplementedError:
                logger.warning(f"Signal handlers are not supported on this platform: {system()}")

        try:
            await run_dashboard(dashboard)
        except asyncio.CancelledError:
            logger.info("Dashboard cancelled.")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting gracefully.")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            logger.info("Goodbye!")


if __name__ == "__main__":
    if system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
